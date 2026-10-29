"""
Manajemen akun user (ADMIN, OPERATOR, PEGAWAI, KADES).

user_id (pelaku) boleh None: endpoint bisa dipakai tanpa token untuk membuat admin pertama
saat tabel users masih kosong (roles_required di routes.py di-comment sementara).
"""
import re

from werkzeug.security import generate_password_hash

from app.core.audit import catat_audit
from app.core.auth import ADMIN, KADES, OPERATOR, PEGAWAI
from app.core.db import get_connection, now_wita
from app.core.errors import AppError, require_fields
from app.modules.kepegawaian import service as kepegawaian

from . import queries as q

ROLES = [ADMIN, OPERATOR, PEGAWAI, KADES]


def _foto_wajah(user):
    """foto_wajah_url dari pegawai yang tertaut; None kalau bukan pegawai / belum punya wajah."""
    return {**user, "foto_wajah_url": kepegawaian.url_foto_wajah(user["id_pegawai"], user["id_wajah"])}


def _get_user(conn, id_user):
    user = q.get_user_by_id(conn, id_user)
    if not user:
        raise AppError("USER_TIDAK_DITEMUKAN", "User tidak ditemukan", 404)
    return _foto_wajah(user)


def _validasi_password(password):
    if not password or len(password) < 5:
        raise AppError("PASSWORD_TERLALU_PENDEK", "Password minimal 5 karakter", 400)


def _payload(conn, payload, id_user=None):
    """Validasi data akun (tanpa password). id_user diisi saat update."""
    require_fields(payload, ["username", "nama"])
    username = str(payload["username"]).strip()
    if not re.fullmatch(r"[A-Za-z0-9_.]{3,50}", username):
        raise AppError("USERNAME_TIDAK_VALID",
                       "Username 3-50 karakter: huruf, angka, titik, atau underscore", 400)

    role = payload.get("role") or ADMIN
    if role not in ROLES:
        raise AppError("ROLE_TIDAK_VALID", f"Role harus salah satu dari: {', '.join(ROLES)}", 400)

    ada = q.get_user_by_username(conn, username)
    if ada and ada["id_user"] != id_user:
        raise AppError("USERNAME_SUDAH_DIPAKAI", f"Username '{username}' sudah dipakai", 409)

    id_pegawai = payload.get("id_pegawai") or None
    if id_pegawai:
        kepegawaian.get_pegawai(conn, id_pegawai)
        tertaut = q.get_user_by_pegawai(conn, id_pegawai)
        if tertaut and tertaut["id_user"] != id_user:
            raise AppError("PEGAWAI_SUDAH_PUNYA_AKUN",
                           f"Pegawai ini sudah tertaut ke akun '{tertaut['username']}'", 409)
    elif role == PEGAWAI:
        raise AppError("PEGAWAI_WAJIB_DIISI", "Role PEGAWAI wajib ditautkan ke data pegawai", 400)

    return {"username": username, "nama": payload["nama"], "role": role, "id_pegawai": id_pegawai}


def _cek_bukan_admin_terakhir(conn, user):
    if user["role"] == ADMIN and q.count_admin_aktif(conn) <= 1:
        raise AppError("ADMIN_TERAKHIR", "Tidak bisa mengubah/menghapus satu-satunya admin aktif", 409)


def list_users(keyword=None, role=None):
    with get_connection().connect() as conn:
        return [_foto_wajah(u) for u in q.list_users(conn, keyword or None, role or None)]


def detail_user(id_user):
    with get_connection().connect() as conn:
        return _get_user(conn, id_user)


def buat_user(conn, payload, user_id):
    """Buat user di dalam transaksi pemanggil. Dipakai juga oleh POST /pegawai."""
    payload = payload or {}
    _validasi_password(payload.get("password"))
    data = _payload(conn, payload)
    id_user = q.insert_user(conn, {**data, "password_hash": generate_password_hash(payload["password"]),
                                   "user": user_id, "now": now_wita()})
    baru = _get_user(conn, id_user)
    catat_audit(conn, user_id, "TAMBAH_USER", "users", id_user, None, baru)
    return baru


def tambah_user(payload, user_id):
    with get_connection().begin() as conn:
        return buat_user(conn, payload, user_id)


def ubah_user(id_user, payload, user_id):
    with get_connection().begin() as conn:
        lama = _get_user(conn, id_user)
        data = _payload(conn, payload, id_user)
        if data["role"] != ADMIN:
            _cek_bukan_admin_terakhir(conn, lama)
        q.update_user(conn, {**data, "id_user": id_user, "user": user_id, "now": now_wita()})
        baru = _get_user(conn, id_user)
        catat_audit(conn, user_id, "UBAH_USER", "users", id_user, lama, baru)
        return baru


def reset_password(id_user, password_baru, user_id):
    _validasi_password(password_baru)
    with get_connection().begin() as conn:
        _get_user(conn, id_user)
        q.update_password(conn, id_user, generate_password_hash(password_baru), user_id, now_wita())
        catat_audit(conn, user_id, "RESET_PASSWORD_USER", "users", id_user)


def hapus_user(id_user, user_id):
    if user_id and id_user == user_id:
        raise AppError("HAPUS_DIRI_SENDIRI", "Tidak bisa menghapus akun sendiri", 409)
    with get_connection().begin() as conn:
        lama = _get_user(conn, id_user)
        _cek_bukan_admin_terakhir(conn, lama)
        q.soft_delete_user(conn, id_user, user_id, now_wita())
        catat_audit(conn, user_id, "HAPUS_USER", "users", id_user, lama, None)
