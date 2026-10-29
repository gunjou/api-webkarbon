"""
Perizinan: pengajuan IZIN / SAKIT / CUTI / DINAS oleh pegawai, proses oleh admin.

Alur status:
  PENDING --setujui--> DISETUJUI --batal (admin)--> DIBATALKAN
     |----tolak----> DITOLAK
     |----batal (pegawai pemilik / admin)--> DIBATALKAN
  Tidak ada hard delete: "hapus" = DIBATALKAN + audit.

Bergantung pada modul lain (lewat service, bukan query langsung):
  kepegawaian.service.get_pegawai(conn, id)          -> pegawai aktif
  absensi.service.buat_absensi_izin(conn, izin, u)   -> DISETUJUI: baris absensi per hari kerja
  absensi.service.hapus_absensi_izin(conn, id_izin)  -> izin disetujui lalu dibatalkan
"""
from app.core import params, storage
from app.core.audit import catat_audit
from app.core.db import get_connection, now_wita
from app.core.errors import AppError, require_fields
from app.modules.absensi import service as absensi
from app.modules.kepegawaian import service as kepegawaian

from . import queries as q

JENIS = ["IZIN", "SAKIT", "CUTI", "DINAS"]
STATUS = ["PENDING", "DISETUJUI", "DITOLAK", "DIBATALKAN"]
PENDING, DISETUJUI, DITOLAK, DIBATALKAN = STATUS
MAKS_HARI = 90


def _out(izin):
    return {**izin, "lampiran_url": f"/api/perizinan/{izin['id_izin']}/lampiran" if izin["lampiran"] else None}


def _get_izin(conn, id_izin, id_pegawai_pemilik=None):
    """id_pegawai_pemilik diisi untuk akses pegawai: hanya boleh izin miliknya sendiri."""
    izin = q.get_izin(conn, id_izin)
    if not izin or (id_pegawai_pemilik and izin["id_pegawai"] != id_pegawai_pemilik):
        raise AppError("IZIN_TIDAK_DITEMUKAN", "Data izin tidak ditemukan", 404)
    return izin


def _filter(args, id_pegawai=None):
    mulai, selesai = params.rentang_tanggal(args)
    return {"mulai": mulai, "selesai": selesai,
            "id_pegawai": id_pegawai or params.bilangan(args.get("id_pegawai"), "id_pegawai"),
            "jenis": params.pilihan(args.get("jenis"), "jenis", JENIS),
            "status": params.pilihan(args.get("status"), "status", STATUS)}


def _halaman(args, id_pegawai=None):
    f = _filter(args, id_pegawai)
    page, per_page, offset = params.halaman(args)
    with get_connection().connect() as conn:
        items = [_out(i) for i in q.list_izin(conn, f, per_page, offset)]
        total = q.count_izin(conn, f)
    return {"items": items, "total": total, "page": page, "per_page": per_page}


def list_izin(args):
    return _halaman(args)


def list_izin_saya(id_pegawai, args):
    return _halaman(args, id_pegawai)


def detail_izin(id_izin, id_pegawai_pemilik=None):
    with get_connection().connect() as conn:
        return _out(_get_izin(conn, id_izin, id_pegawai_pemilik))


def path_lampiran(id_izin, id_pegawai_pemilik=None):
    with get_connection().connect() as conn:
        izin = _get_izin(conn, id_izin, id_pegawai_pemilik)
    if not izin["lampiran"]:
        raise AppError("FILE_TIDAK_DITEMUKAN", "Izin ini tidak punya lampiran", 404)
    return storage.absolute_path(izin["lampiran"])


def ajukan(id_pegawai, form, file, user_id):
    require_fields(form, ["jenis", "tanggal_mulai", "tanggal_selesai", "alasan"])
    jenis = params.pilihan(form.get("jenis"), "jenis", JENIS, wajib=True)
    mulai, selesai = params.rentang_tanggal(form)
    if (selesai - mulai).days + 1 > MAKS_HARI:
        raise AppError("RENTANG_IZIN_TERLALU_PANJANG", f"Maksimal {MAKS_HARI} hari per pengajuan", 400)
    if jenis == "SAKIT" and not (file and file.filename):
        raise AppError("LAMPIRAN_WAJIB", "Izin SAKIT wajib melampirkan surat keterangan / foto", 400)
    with get_connection().begin() as conn:
        kepegawaian.get_pegawai(conn, id_pegawai)
        bentrok = q.get_izin_bentrok(conn, id_pegawai, mulai, selesai)
        if bentrok:
            raise AppError("IZIN_BENTROK", "Sudah ada pengajuan izin di rentang tanggal tersebut", 409, bentrok)
        lampiran = storage.save_upload(file, "izin") if file and file.filename else None
        id_izin = q.insert_izin(conn, {
            "id_pegawai": id_pegawai, "jenis": jenis, "tanggal_mulai": mulai, "tanggal_selesai": selesai,
            "alasan": str(form["alasan"]).strip(), "lampiran": lampiran, "user": user_id, "now": now_wita(),
        })
        baru = q.get_izin(conn, id_izin)
        catat_audit(conn, user_id, "AJUKAN_IZIN", "izin", id_izin, None, baru)
        return _out(baru)


def _ubah_status(conn, lama, status, dari, catatan, user_id):
    ok = q.update_status(conn, {"id_izin": lama["id_izin"], "status": status, "dari": dari,
                                "catatan": catatan, "user": user_id, "now": now_wita()})
    if not ok:
        raise AppError("STATUS_IZIN_TIDAK_VALID",
                       f"Izin berstatus {lama['status_izin']}, tidak bisa diubah ke {status}", 409,
                       {"status_izin": lama["status_izin"]})


def setujui(id_izin, payload, user_id):
    catatan = (payload or {}).get("catatan") or None
    with get_connection().begin() as conn:
        lama = _get_izin(conn, id_izin)
        _ubah_status(conn, lama, DISETUJUI, [PENDING], catatan, user_id)
        dibuat, dilewati = absensi.buat_absensi_izin(conn, lama, user_id)
        baru = q.get_izin(conn, id_izin)
        catat_audit(conn, user_id, "SETUJUI_IZIN", "izin", id_izin, lama,
                    {**baru, "absensi_dibuat": dibuat, "absensi_dilewati": dilewati})
        return {**_out(baru), "absensi_dibuat": dibuat, "absensi_dilewati": dilewati}


def tolak(id_izin, payload, user_id):
    payload = payload or {}
    require_fields(payload, ["catatan"])
    with get_connection().begin() as conn:
        lama = _get_izin(conn, id_izin)
        _ubah_status(conn, lama, DITOLAK, [PENDING], str(payload["catatan"]).strip(), user_id)
        baru = q.get_izin(conn, id_izin)
        catat_audit(conn, user_id, "TOLAK_IZIN", "izin", id_izin, lama, baru)
        return _out(baru)


def batalkan(id_izin, payload, user_id, id_pegawai_pemilik=None):
    """Pegawai: hanya izin miliknya yang masih PENDING.
    Admin: PENDING atau DISETUJUI (baris absensi dari izin ini ikut dihapus)."""
    catatan = (payload or {}).get("catatan") or None
    dari = [PENDING] if id_pegawai_pemilik else [PENDING, DISETUJUI]
    with get_connection().begin() as conn:
        lama = _get_izin(conn, id_izin, id_pegawai_pemilik)
        _ubah_status(conn, lama, DIBATALKAN, dari, catatan, user_id)
        dihapus = absensi.hapus_absensi_izin(conn, id_izin) if lama["status_izin"] == DISETUJUI else []
        baru = q.get_izin(conn, id_izin)
        catat_audit(conn, user_id, "BATALKAN_IZIN", "izin", id_izin, lama, {**baru, "absensi_dihapus": dihapus})
        return _out(baru)
