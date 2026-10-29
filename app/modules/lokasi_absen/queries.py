from sqlalchemy import text

from app.core.db import row, rows

KOLOM_LOKASI = "id_lokasi, nama, latitude, longitude, radius_meter, created_at, updated_at"


def list_lokasi(conn, q=None):
    return rows(conn.execute(text(f"""
        SELECT {KOLOM_LOKASI}
        FROM lokasi_absen
        WHERE status = 1
          AND (CAST(:q AS text) IS NULL OR nama ILIKE '%' || :q || '%')
        ORDER BY nama
    """), {"q": q}))


def get_lokasi_by_id(conn, id_lokasi):
    return row(conn.execute(text(f"""
        SELECT {KOLOM_LOKASI}
        FROM lokasi_absen WHERE id_lokasi = :id AND status = 1
    """), {"id": id_lokasi}))


def get_lokasi_by_nama(conn, nama):
    return row(conn.execute(text("""
        SELECT id_lokasi, nama FROM lokasi_absen
        WHERE lower(nama) = lower(:nama) AND status = 1
    """), {"nama": nama}))


def insert_lokasi(conn, p):
    return conn.execute(text("""
        INSERT INTO lokasi_absen (nama, latitude, longitude, radius_meter, created_by, created_at)
        VALUES (:nama, :latitude, :longitude, :radius_meter, :user, :now)
        RETURNING id_lokasi
    """), p).scalar()


def update_lokasi(conn, p):
    return conn.execute(text("""
        UPDATE lokasi_absen
        SET nama = :nama, latitude = :latitude, longitude = :longitude,
            radius_meter = :radius_meter, updated_by = :user, updated_at = :now
        WHERE id_lokasi = :id_lokasi AND status = 1
        RETURNING id_lokasi
    """), p).scalar()


def soft_delete_lokasi(conn, id_lokasi, user, now):
    return conn.execute(text("""
        UPDATE lokasi_absen SET status = 0, updated_by = :user, updated_at = :now
        WHERE id_lokasi = :id AND status = 1
        RETURNING id_lokasi
    """), {"id": id_lokasi, "user": user, "now": now}).scalar()
