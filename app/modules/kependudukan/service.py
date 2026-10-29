"""
Modul shared. Persuratan memakai get_penduduk() dan cari_by_nik() dari sini.
TODO: import_excel(file) untuk migrasi data penduduk awal.
"""
import re

from app.core.audit import catat_audit
from app.core.db import get_connection, now_wita
from app.core.errors import AppError, require_fields

from . import queries as q

FIELDS = ["nik", "no_kk", "nama", "tempat_lahir", "tgl_lahir", "jenis_kelamin", "agama",
          "status_kawin", "pekerjaan", "kewarganegaraan", "alamat", "dusun", "rt", "rw"]


def validasi_nik(nik, field="nik"):
    if not nik or not re.fullmatch(r"\d{16}", str(nik)):
        raise AppError("NIK_TIDAK_VALID", f"{field.upper()} harus 16 digit angka", 400)


def get_penduduk(conn, id_penduduk):
    """Dipakai lintas modul. Raise 404 kalau tidak ada."""
    p = q.get_penduduk_by_id(conn, id_penduduk)
    if not p:
        raise AppError("PENDUDUK_TIDAK_DITEMUKAN", "Data penduduk tidak ditemukan", 404)
    return p


def cari_by_nik(conn, nik):
    """Dipakai lintas modul. Mengembalikan dict atau None."""
    return q.get_penduduk_by_nik(conn, nik)


def list_penduduk(keyword=None, dusun=None, page=1, per_page=20):
    page = max(int(page), 1)
    per_page = min(max(int(per_page), 1), 100)
    with get_connection().connect() as conn:
        items, total = q.list_penduduk(conn, keyword or None, dusun or None,
                                       per_page, (page - 1) * per_page)
    return {"items": items, "total": total, "page": page, "per_page": per_page}


def detail_penduduk(id_penduduk):
    with get_connection().connect() as conn:
        return get_penduduk(conn, id_penduduk)


def _payload(payload):
    require_fields(payload, ["nik", "nama"])
    validasi_nik(payload["nik"])
    if payload.get("no_kk"):
        validasi_nik(payload["no_kk"], "no_kk")
    if payload.get("jenis_kelamin") not in (None, "", "L", "P"):
        raise AppError("JENIS_KELAMIN_TIDAK_VALID", "Jenis kelamin harus L atau P", 400)
    return {k: (payload.get(k) or None) for k in FIELDS}


def tambah_penduduk(payload, user_id):
    data = _payload(payload)
    with get_connection().begin() as conn:
        ada = q.get_penduduk_by_nik(conn, data["nik"])
        if ada:
            raise AppError("NIK_SUDAH_TERDAFTAR",
                           f"NIK sudah terdaftar atas nama {ada['nama']}", 409,
                           {"id_penduduk": ada["id_penduduk"]})
        id_penduduk = q.insert_penduduk(conn, {**data, "user": user_id, "now": now_wita()})
        return get_penduduk(conn, id_penduduk)


def ubah_penduduk(id_penduduk, payload, user_id):
    data = _payload(payload)
    with get_connection().begin() as conn:
        lama = get_penduduk(conn, id_penduduk)
        ada = q.get_penduduk_by_nik(conn, data["nik"])
        if ada and ada["id_penduduk"] != id_penduduk:
            raise AppError("NIK_SUDAH_TERDAFTAR",
                           f"NIK sudah terdaftar atas nama {ada['nama']}", 409)
        q.update_penduduk(conn, {**data, "id_penduduk": id_penduduk,
                                 "user": user_id, "now": now_wita()})
        baru = get_penduduk(conn, id_penduduk)
        catat_audit(conn, user_id, "UBAH_PENDUDUK", "penduduk", id_penduduk, lama, baru)
        return baru


def hapus_penduduk(id_penduduk, user_id):
    with get_connection().begin() as conn:
        lama = get_penduduk(conn, id_penduduk)
        q.soft_delete_penduduk(conn, id_penduduk, user_id, now_wita())
        catat_audit(conn, user_id, "HAPUS_PENDUDUK", "penduduk", id_penduduk, lama, None)
