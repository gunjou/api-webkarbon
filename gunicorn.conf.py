"""
Konfigurasi gunicorn:  gunicorn -c gunicorn.conf.py wsgi:app

Setiap worker punya engine/pool sendiri. Total koneksi maks ke PostgreSQL:
    workers x (DB_POOL_SIZE + DB_MAX_OVERFLOW)  -> default 3 x (2 + 3) = 15
"""
bind = "0.0.0.0:5000"
workers = 3
timeout = 60


def post_fork(server, worker):
    # Kalau dijalankan dengan --preload, engine dibuat di proses induk lalu ikut ter-fork.
    # Buang koneksi warisan supaya worker tidak berbagi socket database dengan induk.
    from app.core.db import dispose_engine
    dispose_engine(close=False)
