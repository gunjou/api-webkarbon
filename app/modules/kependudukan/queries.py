from sqlalchemy import text

from app.core.db import row, rows

KOLOM = """id_penduduk, nik, no_kk, nama, tempat_lahir, tgl_lahir, jenis_kelamin, agama,
           status_kawin, pekerjaan, kewarganegaraan, alamat, dusun, rt, rw"""

FILTER = """
    WHERE status = 1
      AND (CAST(:q AS text) IS NULL
           OR nik LIKE :q || '%'
           OR lower(nama) LIKE '%' || lower(:q) || '%')
      AND (CAST(:dusun AS text) IS NULL OR dusun = :dusun)
"""


def list_penduduk(conn, q, dusun, limit, offset):
    params = {"q": q, "dusun": dusun, "limit": limit, "offset": offset}
    items = rows(conn.execute(text(f"""
        SELECT {KOLOM} FROM penduduk {FILTER}
        ORDER BY nama
        LIMIT :limit OFFSET :offset
    """), params))
    total = conn.execute(text(f"SELECT count(*) FROM penduduk {FILTER}"), params).scalar()
    return items, total


def get_penduduk_by_id(conn, id_penduduk):
    return row(conn.execute(text(f"""
        SELECT {KOLOM} FROM penduduk WHERE id_penduduk = :id AND status = 1
    """), {"id": id_penduduk}))


def get_penduduk_by_nik(conn, nik):
    return row(conn.execute(text(f"""
        SELECT {KOLOM} FROM penduduk WHERE nik = :nik AND status = 1
    """), {"nik": nik}))


def insert_penduduk(conn, p):
    return conn.execute(text("""
        INSERT INTO penduduk (nik, no_kk, nama, tempat_lahir, tgl_lahir, jenis_kelamin, agama,
                              status_kawin, pekerjaan, kewarganegaraan, alamat, dusun, rt, rw,
                              created_by, created_at)
        VALUES (:nik, :no_kk, :nama, :tempat_lahir, :tgl_lahir, :jenis_kelamin, :agama,
                :status_kawin, :pekerjaan, COALESCE(:kewarganegaraan, 'Indonesia'), :alamat,
                :dusun, :rt, :rw, :user, :now)
        RETURNING id_penduduk
    """), p).scalar()


def update_penduduk(conn, p):
    return conn.execute(text("""
        UPDATE penduduk
        SET nik = :nik, no_kk = :no_kk, nama = :nama, tempat_lahir = :tempat_lahir,
            tgl_lahir = :tgl_lahir, jenis_kelamin = :jenis_kelamin, agama = :agama,
            status_kawin = :status_kawin, pekerjaan = :pekerjaan,
            kewarganegaraan = COALESCE(:kewarganegaraan, 'Indonesia'), alamat = :alamat,
            dusun = :dusun, rt = :rt, rw = :rw, updated_by = :user, updated_at = :now
        WHERE id_penduduk = :id_penduduk AND status = 1
        RETURNING id_penduduk
    """), p).scalar()


def soft_delete_penduduk(conn, id_penduduk, user, now):
    return conn.execute(text("""
        UPDATE penduduk SET status = 0, updated_by = :user, updated_at = :now
        WHERE id_penduduk = :id AND status = 1
        RETURNING id_penduduk
    """), {"id": id_penduduk, "user": user, "now": now}).scalar()
