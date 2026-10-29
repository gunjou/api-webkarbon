from flask_jwt_extended import create_access_token
from werkzeug.security import check_password_hash, generate_password_hash

from app.core.auth import APP_ABSENSI, APP_ADMIN
from app.core.db import get_connection, now_wita
from app.core.errors import AppError
from app.modules.kepegawaian import service as kepegawaian

from . import queries as q


def _public(user):
    return {k: user[k] for k in ("id_user", "username", "nama", "role", "id_pegawai")}


def _token(user, app):
    return create_access_token(
        identity=str(user["id_user"]),
        additional_claims={"role": user["role"], "id_pegawai": user["id_pegawai"], "app": app},
    )


def login(username, password):
    """Login panel admin. Token: app = ADMIN."""
    with get_connection().begin() as conn:
        user = q.get_user_by_username(conn, username)
        if not user or not check_password_hash(user["password_hash"], password):
            raise AppError("LOGIN_GAGAL", "Username atau password salah", 401)
        q.update_last_login(conn, user["id_user"], now_wita())
    return {"access_token": _token(user, APP_ADMIN), "app": APP_ADMIN, "user": _public(user)}


def login_absensi(username, password):
    """Login aplikasi absensi: hanya akun yang tertaut ke pegawai aktif. Token: app = ABSENSI."""
    with get_connection().begin() as conn:
        user = q.get_user_by_username(conn, username)
        if not user or not check_password_hash(user["password_hash"], password):
            raise AppError("LOGIN_GAGAL", "Username atau password salah", 401)
        user = q.get_user_pegawai_by_username(conn, username)
        if not user:
            raise AppError("BUKAN_PEGAWAI", "Akun ini tidak tertaut ke data pegawai aktif", 403)
        q.update_last_login(conn, user["id_user"], now_wita())
        pegawai = kepegawaian.get_pegawai(conn, user["id_pegawai"])
    return {"access_token": _token(user, APP_ABSENSI), "app": APP_ABSENSI,
            "user": _public(user),
            "pegawai": {k: pegawai[k] for k in ("id_pegawai", "nama", "jabatan", "id_wajah", "foto_wajah_url")}}


def get_me(id_user):
    with get_connection().connect() as conn:
        user = q.get_user_by_id(conn, id_user)
    if not user:
        raise AppError("USER_TIDAK_DITEMUKAN", "User tidak ditemukan", 404)
    return _public(user)


def ganti_password(id_user, password_lama, password_baru):
    if len(password_baru) < 5:
        raise AppError("PASSWORD_TERLALU_PENDEK", "Password minimal 5 karakter", 400)

    with get_connection().begin() as conn:
        user = q.get_user_by_id(conn, id_user)
        if not user or not check_password_hash(user["password_hash"], password_lama):
            raise AppError("PASSWORD_LAMA_SALAH", "Password lama salah", 400)
        q.update_password(conn, id_user, generate_password_hash(password_baru), now_wita())
