from sqlalchemy import text

from app.core.db import row, rows

# password_hash sengaja tidak ikut di-SELECT supaya tidak pernah bocor ke response / audit log
# id_wajah: wajah pegawai aktif, NULL kalau user tidak tertaut pegawai / pegawai belum punya wajah
KOLOM = """u.id_user, u.username, u.nama, u.role, u.id_pegawai, p.nama AS nama_pegawai,
           (SELECT max(w.id_wajah) FROM wajah_pegawai w
            WHERE w.id_pegawai = p.id_pegawai AND w.status = 1) AS id_wajah,
           u.last_login_at, u.created_at, u.updated_at"""

FROM = "FROM users u LEFT JOIN pegawai p ON p.id_pegawai = u.id_pegawai AND p.status = 1"


def list_users(conn, q=None, role=None):
    return rows(conn.execute(text(f"""
        SELECT {KOLOM} {FROM}
        WHERE u.status = 1
          -- user yang tertaut ke pegawai nonaktif (status = 0) tidak ditampilkan
          AND (u.id_pegawai IS NULL OR p.id_pegawai IS NOT NULL)
          AND (CAST(:q AS text) IS NULL OR u.username ILIKE '%' || :q || '%' OR u.nama ILIKE '%' || :q || '%')
          AND (CAST(:role AS text) IS NULL OR u.role = :role)
        ORDER BY u.nama
    """), {"q": q, "role": role}))


def get_user_by_id(conn, id_user):
    return row(conn.execute(text(f"""
        SELECT {KOLOM} {FROM} WHERE u.id_user = :id AND u.status = 1
    """), {"id": id_user}))


def get_user_by_username(conn, username):
    return row(conn.execute(text("""
        SELECT id_user, username FROM users WHERE username = :username AND status = 1
    """), {"username": username}))


def get_user_by_pegawai(conn, id_pegawai):
    return row(conn.execute(text("""
        SELECT id_user, username FROM users WHERE id_pegawai = :id AND status = 1
    """), {"id": id_pegawai}))


def count_admin_aktif(conn):
    return conn.execute(text("""
        SELECT count(*) FROM users WHERE role = 'ADMIN' AND status = 1
    """)).scalar()


def insert_user(conn, p):
    return conn.execute(text("""
        INSERT INTO users (username, password_hash, nama, role, id_pegawai, created_by, created_at)
        VALUES (:username, :password_hash, :nama, :role, :id_pegawai, :user, :now)
        RETURNING id_user
    """), p).scalar()


def update_user(conn, p):
    return conn.execute(text("""
        UPDATE users
        SET username = :username, nama = :nama, role = :role, id_pegawai = :id_pegawai,
            updated_by = :user, updated_at = :now
        WHERE id_user = :id_user AND status = 1
        RETURNING id_user
    """), p).scalar()


def update_password(conn, id_user, password_hash, user, now):
    return conn.execute(text("""
        UPDATE users SET password_hash = :password_hash, updated_by = :user, updated_at = :now
        WHERE id_user = :id AND status = 1
        RETURNING id_user
    """), {"id": id_user, "password_hash": password_hash, "user": user, "now": now}).scalar()


def soft_delete_user(conn, id_user, user, now):
    return conn.execute(text("""
        UPDATE users SET status = 0, updated_by = :user, updated_at = :now
        WHERE id_user = :id AND status = 1
        RETURNING id_user
    """), {"id": id_user, "user": user, "now": now}).scalar()
