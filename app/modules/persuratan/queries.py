from sqlalchemy import text

from app.core.db import row, rows


# ---------- jenis surat ----------

def list_jenis_surat(conn):
    return rows(conn.execute(text("""
        SELECT id_jenis_surat, kode, nama, judul_surat, kode_klasifikasi, pakai_subjek, field_schema
        FROM jenis_surat
        WHERE status = 1
        ORDER BY urutan, nama
    """)))


def get_jenis_surat_by_id(conn, id_jenis_surat):
    return row(conn.execute(text("""
        SELECT id_jenis_surat, kode, nama, judul_surat, kode_klasifikasi, pakai_subjek,
               field_schema, template_isi
        FROM jenis_surat
        WHERE id_jenis_surat = :id AND status = 1
    """), {"id": id_jenis_surat}))


# ---------- penandatangan ----------

def list_penandatangan(conn):
    return rows(conn.execute(text("""
        SELECT t.id_penandatangan, t.id_pegawai, p.nama, t.jabatan_label, t.mode, t.is_default
        FROM penandatangan t
        JOIN pegawai p ON p.id_pegawai = t.id_pegawai AND p.status = 1
        WHERE t.status = 1
        ORDER BY t.is_default DESC, p.nama
    """)))


def get_penandatangan_by_id(conn, id_penandatangan):
    return row(conn.execute(text("""
        SELECT t.id_penandatangan, p.nama, t.jabatan_label, t.mode
        FROM penandatangan t
        JOIN pegawai p ON p.id_pegawai = t.id_pegawai AND p.status = 1
        WHERE t.id_penandatangan = :id AND t.status = 1
    """), {"id": id_penandatangan}))


# ---------- surat ----------

def insert_surat_draft(conn, p):
    return conn.execute(text("""
        INSERT INTO surat (id_jenis_surat, id_penduduk, data, id_penandatangan,
                           status_surat, created_by, created_at)
        VALUES (:id_jenis_surat, :id_penduduk, CAST(:data AS jsonb), :id_penandatangan,
                'DRAFT', :user, :now)
        RETURNING id_surat
    """), p).scalar()


def update_surat_draft(conn, p):
    return conn.execute(text("""
        UPDATE surat
        SET id_penduduk = :id_penduduk, data = CAST(:data AS jsonb),
            id_penandatangan = :id_penandatangan, updated_by = :user, updated_at = :now
        WHERE id_surat = :id_surat AND status_surat = 'DRAFT'
        RETURNING id_surat
    """), p).scalar()


def get_surat_by_id(conn, id_surat):
    return row(conn.execute(text("""
        SELECT s.id_surat, s.id_jenis_surat, j.nama AS nama_jenis, j.kode AS kode_jenis,
               s.status_surat, s.id_penduduk, s.data, s.id_penandatangan, s.penandatangan,
               s.nomor_urut, s.nomor_surat, s.tanggal_surat, s.file_pdf, s.alasan_batal,
               s.created_by, s.created_at, s.updated_at, s.finalized_by, s.finalized_at,
               s.dibatalkan_by, s.dibatalkan_at
        FROM surat s
        JOIN jenis_surat j ON j.id_jenis_surat = s.id_jenis_surat
        WHERE s.id_surat = :id
    """), {"id": id_surat}))


FILTER_SURAT = """
    WHERE (CAST(:id_jenis_surat AS int) IS NULL OR s.id_jenis_surat = :id_jenis_surat)
      AND (CAST(:status_surat AS text) IS NULL OR s.status_surat = :status_surat)
      AND (CAST(:tahun AS int) IS NULL
           OR EXTRACT(YEAR FROM COALESCE(s.tanggal_surat, s.created_at::date)) = :tahun)
      AND (CAST(:q AS text) IS NULL
           OR s.nomor_surat ILIKE '%' || :q || '%'
           OR s.data->'subjek'->>'nik' LIKE :q || '%'
           OR s.data->'subjek'->>'nama' ILIKE '%' || :q || '%')
"""


def list_surat(conn, f, limit, offset):
    params = {**f, "limit": limit, "offset": offset}
    items = rows(conn.execute(text(f"""
        SELECT s.id_surat, j.nama AS nama_jenis, s.status_surat, s.nomor_surat, s.tanggal_surat,
               s.data->'subjek'->>'nik' AS nik, s.data->'subjek'->>'nama' AS nama,
               s.data->>'keperluan' AS keperluan, s.created_at
        FROM surat s
        JOIN jenis_surat j ON j.id_jenis_surat = s.id_jenis_surat
        {FILTER_SURAT}
        ORDER BY s.created_at DESC
        LIMIT :limit OFFSET :offset
    """), params))
    total = conn.execute(text(f"SELECT count(*) FROM surat s {FILTER_SURAT}"), params).scalar()
    return items, total


# ---------- penomoran ----------

def next_nomor_urut(conn, scope, tahun):
    """Atomik: aman walau dua admin finalisasi bersamaan. Ikut rollback bila transaksi gagal."""
    return conn.execute(text("""
        INSERT INTO nomor_counter (scope, tahun, last_number) VALUES (:scope, :tahun, 1)
        ON CONFLICT (scope, tahun)
        DO UPDATE SET last_number = nomor_counter.last_number + 1
        RETURNING last_number
    """), {"scope": scope, "tahun": tahun}).scalar()
