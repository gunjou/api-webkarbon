"""
Lokasi absen (titik pusat + radius geofence).
Modul absensi memakai list_lokasi_aktif(conn) di bawah untuk cek radius saat check-in,
bukan query langsung ke tabel lokasi_absen.
"""
from app.core.audit import catat_audit
from app.core.db import get_connection, now_wita
from app.core.errors import AppError, require_fields

from . import queries as q


def list_lokasi_aktif(conn):
    """Dipakai lintas modul (absensi). Semua lokasi aktif."""
    return q.list_lokasi(conn)


def _lokasi_payload(payload):
    require_fields(payload, ["nama", "latitude", "longitude"])
    try:
        lat, lng = float(payload["latitude"]), float(payload["longitude"])
        radius = int(payload.get("radius_meter") or 100)
    except (TypeError, ValueError):
        raise AppError("KOORDINAT_TIDAK_VALID", "Latitude/longitude/radius harus berupa angka", 400)
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise AppError("KOORDINAT_TIDAK_VALID", "Koordinat di luar rentang", 400)
    if not (10 <= radius <= 1000):
        raise AppError("RADIUS_TIDAK_VALID", "Radius harus antara 10 - 1000 meter", 400)
    return {"nama": str(payload["nama"]).strip(), "latitude": lat, "longitude": lng, "radius_meter": radius}


def _get_lokasi(conn, id_lokasi):
    lokasi = q.get_lokasi_by_id(conn, id_lokasi)
    if not lokasi:
        raise AppError("LOKASI_TIDAK_DITEMUKAN", "Lokasi absen tidak ditemukan", 404)
    return lokasi


def _cek_nama_lokasi(conn, nama, id_lokasi=None):
    ada = q.get_lokasi_by_nama(conn, nama)
    if ada and ada["id_lokasi"] != id_lokasi:
        raise AppError("LOKASI_SUDAH_ADA", f"Lokasi dengan nama '{ada['nama']}' sudah ada", 409)


def list_lokasi(keyword=None):
    with get_connection().connect() as conn:
        return q.list_lokasi(conn, keyword or None)


def detail_lokasi(id_lokasi):
    with get_connection().connect() as conn:
        return _get_lokasi(conn, id_lokasi)


def tambah_lokasi(payload, user_id):
    data = _lokasi_payload(payload)
    with get_connection().begin() as conn:
        _cek_nama_lokasi(conn, data["nama"])
        id_lokasi = q.insert_lokasi(conn, {**data, "user": user_id, "now": now_wita()})
        baru = _get_lokasi(conn, id_lokasi)
        catat_audit(conn, user_id, "TAMBAH_LOKASI_ABSEN", "lokasi_absen", id_lokasi, None, baru)
        return baru


def ubah_lokasi(id_lokasi, payload, user_id):
    data = _lokasi_payload(payload)
    with get_connection().begin() as conn:
        lama = _get_lokasi(conn, id_lokasi)
        _cek_nama_lokasi(conn, data["nama"], id_lokasi)
        q.update_lokasi(conn, {**data, "id_lokasi": id_lokasi, "user": user_id, "now": now_wita()})
        baru = _get_lokasi(conn, id_lokasi)
        catat_audit(conn, user_id, "UBAH_LOKASI_ABSEN", "lokasi_absen", id_lokasi, lama, baru)
        return baru


def hapus_lokasi(id_lokasi, user_id):
    with get_connection().begin() as conn:
        lama = _get_lokasi(conn, id_lokasi)
        q.soft_delete_lokasi(conn, id_lokasi, user_id, now_wita())
        catat_audit(conn, user_id, "HAPUS_LOKASI_ABSEN", "lokasi_absen", id_lokasi, lama, None)
