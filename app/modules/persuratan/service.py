"""
Alur surat: DRAFT -> (preview) -> FINAL (nomor terbit + PDF) / BATAL.

Subjek surat (data.subjek) selalu snapshot:
  Opsi A: id_penduduk diisi  -> data disalin dari tabel penduduk
  Opsi B: subjek diisi manual -> untuk penduduk yang belum terdaftar
Template hanya membaca data.subjek, jadi setelah draft tersimpan kedua opsi diperlakukan sama.

Sudah: list jenis surat, penandatangan, buat/ubah draft, detail, list (register).
Berikutnya: preview_pdf(), finalisasi(), batalkan(), export_register().
"""
import json

import bleach

from app.core.db import get_connection, json_default, now_wita
from app.core.errors import AppError, require_fields
from app.modules.kependudukan import service as kependudukan
from app.modules.pengaturan.queries import get_pengaturan

from . import queries as q

SUBJEK_FIELDS = ["nik", "nama", "tempat_lahir", "tgl_lahir", "jenis_kelamin", "agama",
                 "status_kawin", "pekerjaan", "kewarganegaraan", "alamat_lengkap"]
SUBJEK_WAJIB = ["nik", "nama", "tempat_lahir", "tgl_lahir", "jenis_kelamin", "alamat_lengkap"]
RICHTEXT_TAGS = {"p", "br", "b", "strong", "i", "em", "u", "ol", "ul", "li", "table", "tr", "td", "th"}


# ---------- referensi ----------

def list_jenis_surat():
    with get_connection().connect() as conn:
        return q.list_jenis_surat(conn)


def list_penandatangan():
    with get_connection().connect() as conn:
        return q.list_penandatangan(conn)


# ---------- helper ----------

def _get_jenis(conn, id_jenis_surat):
    jenis = q.get_jenis_surat_by_id(conn, id_jenis_surat)
    if not jenis:
        raise AppError("JENIS_SURAT_TIDAK_DITEMUKAN", "Jenis surat tidak ditemukan", 404)
    return jenis


def _get_surat(conn, id_surat):
    surat = q.get_surat_by_id(conn, id_surat)
    if not surat:
        raise AppError("SURAT_TIDAK_DITEMUKAN", "Surat tidak ditemukan", 404)
    return surat


def _alamat_lengkap(penduduk, desa):
    bagian = [
        penduduk.get("alamat"),
        f"Dusun {penduduk['dusun']}" if penduduk.get("dusun") else None,
        f"RT {penduduk['rt']}" if penduduk.get("rt") else None,
        f"RW {penduduk['rw']}" if penduduk.get("rw") else None,
        f"Desa {desa.get('nama')}" if desa.get("nama") else None,
        f"Kecamatan {desa.get('kecamatan')}" if desa.get("kecamatan") else None,
        f"Kabupaten {desa.get('kabupaten')}" if desa.get("kabupaten") else None,
    ]
    return " ".join(b for b in bagian if b)


def _validasi_isian(field_schema, isian):
    """Validasi isian terhadap field_schema jenis surat."""
    isian = isian or {}
    kurang = [f["name"] for f in field_schema
              if f.get("required") and isian.get(f["name"]) in (None, "", [])]
    if kurang:
        raise AppError("ISIAN_TIDAK_LENGKAP", f"Isian wajib belum diisi: {', '.join(kurang)}",
                       400, {"fields": kurang})
    for f in field_schema:
        nilai = isian.get(f["name"])
        if f.get("type") == "select" and nilai not in (None, "") and nilai not in f.get("options", []):
            raise AppError("ISIAN_TIDAK_VALID", f"Pilihan '{f['label']}' tidak valid", 400)
    # hanya simpan field yang terdaftar di schema; richtext disanitasi (dirender dengan |safe)
    hasil = {}
    for f in field_schema:
        nilai = isian.get(f["name"])
        if f.get("type") == "richtext" and nilai:
            nilai = bleach.clean(nilai, tags=RICHTEXT_TAGS, attributes={}, strip=True)
        hasil[f["name"]] = nilai
    return hasil


def _susun_subjek(conn, payload, jenis):
    """Mengembalikan (id_penduduk, subjek). Inti dari opsi A / opsi B."""
    if not jenis["pakai_subjek"]:
        return None, None

    if payload.get("id_penduduk"):                                   # Opsi A
        p = kependudukan.get_penduduk(conn, payload["id_penduduk"])
        desa = get_pengaturan(conn, "desa", {})
        subjek = {k: p.get(k) for k in SUBJEK_FIELDS if k != "alamat_lengkap"}
        subjek["alamat_lengkap"] = _alamat_lengkap(p, desa)
        return p["id_penduduk"], subjek

    subjek_in = payload.get("subjek") or {}                          # Opsi B
    subjek = {k: subjek_in.get(k) for k in SUBJEK_FIELDS}
    subjek["kewarganegaraan"] = subjek.get("kewarganegaraan") or "Indonesia"
    kurang = [k for k in SUBJEK_WAJIB if not subjek.get(k)]
    if kurang:
        raise AppError("SUBJEK_TIDAK_LENGKAP", f"Data diri wajib diisi: {', '.join(kurang)}",
                       400, {"fields": kurang})
    kependudukan.validasi_nik(subjek["nik"])

    terdaftar = kependudukan.cari_by_nik(conn, subjek["nik"])
    if terdaftar and not payload.get("abaikan_nik_terdaftar"):
        raise AppError("NIK_SUDAH_TERDAFTAR",
                       f"NIK ini sudah terdaftar atas nama {terdaftar['nama']}", 409,
                       {"id_penduduk": terdaftar["id_penduduk"]})
    return None, subjek


def _susun_data(conn, payload, jenis):
    id_penduduk, subjek = _susun_subjek(conn, payload, jenis)
    data = {
        "subjek": subjek,
        "keperluan": payload.get("keperluan"),
        "isian": _validasi_isian(jenis["field_schema"], payload.get("isian")),
    }
    if payload.get("id_penandatangan") and not q.get_penandatangan_by_id(conn, payload["id_penandatangan"]):
        raise AppError("PENANDATANGAN_TIDAK_DITEMUKAN", "Penandatangan tidak ditemukan", 404)
    return id_penduduk, data


# ---------- draft ----------

def buat_draft(payload, user_id):
    require_fields(payload, ["id_jenis_surat"])
    with get_connection().begin() as conn:
        jenis = _get_jenis(conn, payload["id_jenis_surat"])
        id_penduduk, data = _susun_data(conn, payload, jenis)
        id_surat = q.insert_surat_draft(conn, {
            "id_jenis_surat": jenis["id_jenis_surat"],
            "id_penduduk": id_penduduk,
            "data": json.dumps(data, default=json_default),
            "id_penandatangan": payload.get("id_penandatangan"),
            "user": user_id,
            "now": now_wita(),
        })
        return q.get_surat_by_id(conn, id_surat)    # conn yang sama -> data terbaru


def ubah_draft(id_surat, payload, user_id):
    with get_connection().begin() as conn:
        surat = _get_surat(conn, id_surat)
        if surat["status_surat"] != "DRAFT":
            raise AppError("SURAT_SUDAH_FINAL", "Hanya surat berstatus DRAFT yang bisa diubah", 409)
        jenis = _get_jenis(conn, surat["id_jenis_surat"])
        id_penduduk, data = _susun_data(conn, payload, jenis)
        q.update_surat_draft(conn, {
            "id_surat": id_surat,
            "id_penduduk": id_penduduk,
            "data": json.dumps(data, default=json_default),
            "id_penandatangan": payload.get("id_penandatangan"),
            "user": user_id,
            "now": now_wita(),
        })
        return q.get_surat_by_id(conn, id_surat)


# ---------- baca ----------

def detail_surat(id_surat):
    with get_connection().connect() as conn:
        return _get_surat(conn, id_surat)


def list_surat(args):
    page = max(int(args.get("page", 1)), 1)
    per_page = min(max(int(args.get("per_page", 20)), 1), 100)
    f = {
        "id_jenis_surat": args.get("id_jenis_surat", type=int),
        "status_surat": args.get("status_surat") or None,
        "tahun": args.get("tahun", type=int),
        "q": args.get("q") or None,
    }
    with get_connection().connect() as conn:
        items, total = q.list_surat(conn, f, per_page, (page - 1) * per_page)
    return {"items": items, "total": total, "page": page, "per_page": per_page}


# ---------- berikutnya ----------
# def preview_pdf(id_surat): render tanpa nomor, tidak disimpan
# def finalisasi(id_surat, user_id):
#     with get_connection().begin() as conn:
#         urut = q.next_nomor_urut(conn, scope, tahun) -> susun nomor_surat
#         snapshot penandatangan -> renderer.render_pdf() -> storage.save_bytes()
#         UPDATE status FINAL
# def batalkan(id_surat, alasan, user_id): status BATAL + catat_audit
# def export_register(args): xlsx
