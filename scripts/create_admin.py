"""
Buat user ADMIN pertama.
    python -m scripts.create_admin
"""
import getpass

from sqlalchemy import text
from werkzeug.security import generate_password_hash

from app.config import Config
from app.core.db import dispose_engine, get_connection, init_engine, now_wita


def main():
    init_engine(Config.DATABASE_URL)
    username = input("Username admin: ").strip()
    nama = input("Nama lengkap  : ").strip()
    password = getpass.getpass("Password (min 8): ")
    if len(password) < 8:
        raise SystemExit("Password minimal 8 karakter")

    with get_connection().begin() as conn:
        ada = conn.execute(text("SELECT 1 FROM users WHERE username = :u AND status = 1"),
                           {"u": username}).scalar()
        if ada:
            raise SystemExit(f"Username '{username}' sudah ada")
        id_user = conn.execute(text("""
            INSERT INTO users (username, password_hash, nama, role, created_at)
            VALUES (:username, :password_hash, :nama, 'ADMIN', :now)
            RETURNING id_user
        """), {"username": username, "password_hash": generate_password_hash(password),
               "nama": nama, "now": now_wita()}).scalar()
    print(f"Admin dibuat (id_user={id_user})")


if __name__ == "__main__":
    try:
        main()
    finally:
        dispose_engine()
