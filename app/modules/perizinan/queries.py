from sqlalchemy import text

from app.core.db import row, rows

KOLOM = """i.id_izin, i.id_pegawai, p.nama AS nama_pegawai, p.jabatan, i.jenis,
           i.tanggal_mulai, i.tanggal_selesai, (i.tanggal_selesai - i.tanggal_mulai + 1) AS jumlah_hari,
           i.alasan, i.lampiran, i.status_izin, i.catatan_proses,
           i.diproses_by, u.username AS diproses_oleh, i.diproses_at,
           i.created_by, i.created_at, i.updated_by, i.updated_at"""

FROM = """FROM izin i
          JOIN pegawai p ON p.id_pegawai = i.id_pegawai
          LEFT JOIN users u ON u.id_user = i.diproses_by"""

FILTER = """WHERE (CAST(:mulai AS date) IS NULL OR i.tanggal_selesai >= :mulai)
              AND (CAST(:selesai AS date) IS NULL OR i.tanggal_mulai <= :selesai)
              AND (CAST(:id_pegawai AS int) IS NULL OR i.id_pegawai = :id_pegawai)
              AND (CAST(:jenis AS text) IS NULL OR i.jenis = :jenis)
              AND (CAST(:status AS text) IS NULL OR i.status_izin = :status)"""


def get_izin(conn, id_izin):
    return row(conn.execute(text(f"SELECT {KOLOM} {FROM} WHERE i.id_izin = :id"), {"id": id_izin}))


def list_izin(conn, f, limit, offset):
    return rows(conn.execute(text(f"""
        SELECT {KOLOM} {FROM} {FILTER}
        ORDER BY (i.status_izin = 'PENDING') DESC, i.created_at DESC
        LIMIT :limit OFFSET :offset
    """), {**f, "limit": limit, "offset": offset}))


def count_izin(conn, f):
    return conn.execute(text(f"SELECT count(*) {FROM} {FILTER}"), f).scalar()


def get_izin_bentrok(conn, id_pegawai, mulai, selesai):
    """Izin PENDING/DISETUJUI milik pegawai yang tanggalnya beririsan."""
    return row(conn.execute(text("""
        SELECT id_izin, jenis, tanggal_mulai, tanggal_selesai, status_izin FROM izin
        WHERE id_pegawai = :id_pegawai AND status_izin IN ('PENDING', 'DISETUJUI')
          AND tanggal_mulai <= :selesai AND tanggal_selesai >= :mulai
        LIMIT 1
    """), {"id_pegawai": id_pegawai, "mulai": mulai, "selesai": selesai}))


def insert_izin(conn, p):
    return conn.execute(text("""
        INSERT INTO izin (id_pegawai, jenis, tanggal_mulai, tanggal_selesai, alasan, lampiran,
                          created_by, created_at)
        VALUES (:id_pegawai, :jenis, :tanggal_mulai, :tanggal_selesai, :alasan, :lampiran, :user, :now)
        RETURNING id_izin
    """), p).scalar()


def update_status(conn, p):
    """Hanya berhasil kalau status masih salah satu dari :dari (cegah proses ganda)."""
    return conn.execute(text("""
        UPDATE izin
        SET status_izin = :status, catatan_proses = :catatan, diproses_by = :user, diproses_at = :now,
            updated_by = :user, updated_at = :now
        WHERE id_izin = :id_izin AND status_izin = ANY(:dari)
        RETURNING id_izin
    """), p).scalar()
