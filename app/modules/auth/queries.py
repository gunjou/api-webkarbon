from sqlalchemy import text

from app.core.db import row


def get_user_by_username(conn, username):
    return row(conn.execute(text("""
        SELECT id_user, username, password_hash, nama, role, id_pegawai
        FROM users
        WHERE username = :username AND status = 1
    """), {"username": username}))


def get_user_pegawai_by_username(conn, username):
    """Hanya akun yang tertaut ke pegawai AKTIF (untuk login aplikasi absensi)."""
    return row(conn.execute(text("""
        SELECT u.id_user, u.username, u.password_hash, u.nama, u.role, u.id_pegawai,
               p.nama AS nama_pegawai, p.jabatan
        FROM users u JOIN pegawai p ON p.id_pegawai = u.id_pegawai AND p.status = 1
        WHERE u.username = :username AND u.status = 1
    """), {"username": username}))


def get_user_by_id(conn, id_user):
    return row(conn.execute(text("""
        SELECT id_user, username, password_hash, nama, role, id_pegawai, last_login_at
        FROM users
        WHERE id_user = :id_user AND status = 1
    """), {"id_user": id_user}))


def update_last_login(conn, id_user, now):
    conn.execute(text("""
        UPDATE users SET last_login_at = :now WHERE id_user = :id_user
    """), {"id_user": id_user, "now": now})


def update_password(conn, id_user, password_hash, now):
    conn.execute(text("""
        UPDATE users
        SET password_hash = :password_hash, updated_by = :id_user, updated_at = :now
        WHERE id_user = :id_user AND status = 1
    """), {"id_user": id_user, "password_hash": password_hash, "now": now})
