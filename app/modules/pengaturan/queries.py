"""
Modul sederhana: tidak perlu service.py.
get_pengaturan() juga dipakai modul lain (persuratan, absensi) sebagai pintu baca konfigurasi.
"""
import json

from sqlalchemy import text

from app.core.db import json_default, row, rows


def get_all(conn):
    return rows(conn.execute(text("""
        SELECT key, value, updated_by, updated_at FROM pengaturan ORDER BY key
    """)))


def get_pengaturan(conn, key, default=None):
    r = row(conn.execute(text("SELECT value FROM pengaturan WHERE key = :key"), {"key": key}))
    return r["value"] if r else default


def upsert(conn, key, value, updated_by, now):
    conn.execute(text("""
        INSERT INTO pengaturan (key, value, updated_by, updated_at)
        VALUES (:key, CAST(:value AS jsonb), :updated_by, :now)
        ON CONFLICT (key) DO UPDATE
        SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by, updated_at = EXCLUDED.updated_at
    """), {"key": key, "value": json.dumps(value, default=json_default),
           "updated_by": updated_by, "now": now})
