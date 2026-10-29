from sqlalchemy import text

from app.core.db import row, rows

# id_wajah: foto wajah aktif pegawai, NULL kalau belum ada
KOLOM = """id_pegawai, nama, nik, jabatan, no_hp, tanggal_mulai, created_at, updated_at,
           (SELECT max(w.id_wajah) FROM wajah_pegawai w
            WHERE w.id_pegawai = pegawai.id_pegawai AND w.status = 1) AS id_wajah"""


def list_pegawai(conn, q=None):
    return rows(conn.execute(text(f"""
        SELECT {KOLOM}
        FROM pegawai
        WHERE status = 1
          AND (CAST(:q AS text) IS NULL OR nama ILIKE '%' || :q || '%' OR jabatan ILIKE '%' || :q || '%')
        ORDER BY nama
    """), {"q": q}))


def get_pegawai_by_id(conn, id_pegawai):
    return row(conn.execute(text(f"""
        SELECT {KOLOM} FROM pegawai WHERE id_pegawai = :id AND status = 1
    """), {"id": id_pegawai}))


def insert_pegawai(conn, p):
    return conn.execute(text("""
        INSERT INTO pegawai (nama, nik, jabatan, no_hp, tanggal_mulai, created_by, created_at)
        VALUES (:nama, :nik, :jabatan, :no_hp, :tanggal_mulai, :user, :now)
        RETURNING id_pegawai
    """), p).scalar()


def update_pegawai(conn, p):
    return conn.execute(text("""
        UPDATE pegawai
        SET nama = :nama, nik = :nik, jabatan = :jabatan, no_hp = :no_hp,
            tanggal_mulai = :tanggal_mulai, updated_by = :user, updated_at = :now
        WHERE id_pegawai = :id_pegawai AND status = 1
        RETURNING id_pegawai
    """), p).scalar()


def soft_delete_pegawai(conn, id_pegawai, user, now):
    return conn.execute(text("""
        UPDATE pegawai SET status = 0, updated_by = :user, updated_at = :now
        WHERE id_pegawai = :id AND status = 1
        RETURNING id_pegawai
    """), {"id": id_pegawai, "user": user, "now": now}).scalar()


def kunci_pegawai(conn, id_pegawai):
    """Row lock pegawai sampai transaksi selesai (cegah 2 simpan wajah bersamaan)."""
    conn.execute(text("SELECT 1 FROM pegawai WHERE id_pegawai = :id FOR UPDATE"), {"id": id_pegawai})


# ---------- wajah pegawai (1 wajah aktif per pegawai) ----------
# embedding sengaja tidak ikut di KOLOM_WAJAH (besar & tidak berguna untuk frontend)

KOLOM_WAJAH = "id_wajah, id_pegawai, foto_path, created_at"


def get_wajah(conn, id_pegawai):
    return row(conn.execute(text(f"""
        SELECT {KOLOM_WAJAH} FROM wajah_pegawai
        WHERE id_pegawai = :id AND status = 1
        ORDER BY id_wajah DESC LIMIT 1
    """), {"id": id_pegawai}))


def get_embedding_wajah(conn, id_pegawai):
    return conn.execute(text("""
        SELECT embedding FROM wajah_pegawai
        WHERE id_pegawai = :id AND status = 1
        ORDER BY id_wajah DESC LIMIT 1
    """), {"id": id_pegawai}).scalar()


def insert_wajah(conn, p):
    return conn.execute(text("""
        INSERT INTO wajah_pegawai (id_pegawai, embedding, foto_path, created_by, created_at)
        VALUES (:id_pegawai, :embedding, :foto_path, :user, :now)
        RETURNING id_wajah
    """), p).scalar()


def soft_delete_wajah(conn, id_pegawai):
    return conn.execute(text("""
        UPDATE wajah_pegawai SET status = 0
        WHERE id_pegawai = :id AND status = 1
    """), {"id": id_pegawai}).rowcount
