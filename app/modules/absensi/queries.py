from sqlalchemy import text

from app.core.db import row, rows

# ---------- absensi ----------

KOLOM = """a.id_absensi, a.id_pegawai, p.nama AS nama_pegawai, p.jabatan, a.tanggal, a.status_kehadiran,
           a.id_izin, a.jadwal_masuk, a.jadwal_pulang, a.toleransi_menit,
           a.jam_masuk, a.lat_masuk, a.lng_masuk, a.akurasi_masuk, a.id_lokasi_masuk,
           lm.nama AS nama_lokasi_masuk, a.foto_masuk, a.skor_masuk,
           a.jam_pulang, a.lat_pulang, a.lng_pulang, a.akurasi_pulang, a.id_lokasi_pulang,
           lp.nama AS nama_lokasi_pulang, a.foto_pulang, a.skor_pulang,
           a.menit_telat, a.menit_pulang_cepat, a.keterangan, a.is_koreksi,
           a.created_by, a.created_at, a.updated_by, a.updated_at"""

FROM = """FROM absensi a
          JOIN pegawai p ON p.id_pegawai = a.id_pegawai
          LEFT JOIN lokasi_absen lm ON lm.id_lokasi = a.id_lokasi_masuk
          LEFT JOIN lokasi_absen lp ON lp.id_lokasi = a.id_lokasi_pulang"""

FILTER = """WHERE (CAST(:mulai AS date) IS NULL OR a.tanggal >= :mulai)
              AND (CAST(:selesai AS date) IS NULL OR a.tanggal <= :selesai)
              AND (CAST(:id_pegawai AS int) IS NULL OR a.id_pegawai = :id_pegawai)
              AND (CAST(:status AS text) IS NULL OR a.status_kehadiran = :status)"""


def get_absensi(conn, id_absensi):
    return row(conn.execute(text(f"SELECT {KOLOM} {FROM} WHERE a.id_absensi = :id"), {"id": id_absensi}))


def get_absensi_harian(conn, id_pegawai, tanggal):
    return row(conn.execute(text(f"""
        SELECT {KOLOM} {FROM} WHERE a.id_pegawai = :id_pegawai AND a.tanggal = :tanggal
    """), {"id_pegawai": id_pegawai, "tanggal": tanggal}))


def list_absensi(conn, f, limit, offset):
    return rows(conn.execute(text(f"""
        SELECT {KOLOM} {FROM} {FILTER}
        ORDER BY a.tanggal DESC, p.nama
        LIMIT :limit OFFSET :offset
    """), {**f, "limit": limit, "offset": offset}))


def count_absensi(conn, f):
    return conn.execute(text(f"SELECT count(*) {FROM} {FILTER}"), f).scalar()


def list_absensi_periode(conn, id_pegawai, mulai, selesai):
    """Semua absensi dalam rentang (untuk riwayat, monitor & rekap). id_pegawai None = semua."""
    return rows(conn.execute(text(f"""
        SELECT {KOLOM} {FROM}
        WHERE a.tanggal BETWEEN :mulai AND :selesai
          AND (CAST(:id_pegawai AS int) IS NULL OR a.id_pegawai = :id_pegawai)
        ORDER BY a.tanggal, p.nama
    """), {"id_pegawai": id_pegawai, "mulai": mulai, "selesai": selesai}))


def insert_masuk(conn, p):
    """ON CONFLICT DO NOTHING: kalau 2 request masuk bersamaan, yang kedua dapat None."""
    return conn.execute(text("""
        INSERT INTO absensi (id_pegawai, tanggal, status_kehadiran,
                             jadwal_masuk, jadwal_pulang, toleransi_menit,
                             jam_masuk, lat_masuk, lng_masuk, akurasi_masuk, id_lokasi_masuk,
                             foto_masuk, skor_masuk, menit_telat, created_by, created_at)
        VALUES (:id_pegawai, :tanggal, 'HADIR',
                :jadwal_masuk, :jadwal_pulang, :toleransi_menit,
                :jam, :lat, :lng, :akurasi, :id_lokasi,
                :foto, :skor, :menit_telat, :user, :now)
        ON CONFLICT (id_pegawai, tanggal) DO NOTHING
        RETURNING id_absensi
    """), p).scalar()


def update_pulang(conn, p):
    """WHERE jam_pulang IS NULL: kalau 2 request pulang bersamaan, yang kedua dapat None."""
    return conn.execute(text("""
        UPDATE absensi
        SET jam_pulang = :jam, lat_pulang = :lat, lng_pulang = :lng, akurasi_pulang = :akurasi,
            id_lokasi_pulang = :id_lokasi, foto_pulang = :foto, skor_pulang = :skor,
            menit_pulang_cepat = :menit_pulang_cepat, updated_by = :user, updated_at = :now
        WHERE id_absensi = :id_absensi AND jam_masuk IS NOT NULL AND jam_pulang IS NULL
        RETURNING id_absensi
    """), p).scalar()


def insert_manual(conn, p):
    return conn.execute(text("""
        INSERT INTO absensi (id_pegawai, tanggal, status_kehadiran,
                             jadwal_masuk, jadwal_pulang, toleransi_menit,
                             jam_masuk, jam_pulang, menit_telat, menit_pulang_cepat,
                             keterangan, is_koreksi, created_by, created_at)
        VALUES (:id_pegawai, :tanggal, :status_kehadiran,
                :jadwal_masuk, :jadwal_pulang, :toleransi_menit,
                :jam_masuk, :jam_pulang, :menit_telat, :menit_pulang_cepat,
                :keterangan, TRUE, :user, :now)
        ON CONFLICT (id_pegawai, tanggal) DO NOTHING
        RETURNING id_absensi
    """), p).scalar()


def update_koreksi(conn, p):
    return conn.execute(text("""
        UPDATE absensi
        SET status_kehadiran = :status_kehadiran, jam_masuk = :jam_masuk, jam_pulang = :jam_pulang,
            menit_telat = :menit_telat, menit_pulang_cepat = :menit_pulang_cepat,
            keterangan = :keterangan, is_koreksi = TRUE, updated_by = :user, updated_at = :now
        WHERE id_absensi = :id_absensi
        RETURNING id_absensi
    """), p).scalar()


def delete_absensi(conn, id_absensi):
    return conn.execute(text("DELETE FROM absensi WHERE id_absensi = :id RETURNING id_absensi"),
                        {"id": id_absensi}).scalar()


def insert_izin(conn, p):
    """Baris absensi dari izin DISETUJUI. Hari yang sudah ada absensinya dilewati (None)."""
    return conn.execute(text("""
        INSERT INTO absensi (id_pegawai, tanggal, status_kehadiran, id_izin,
                             jadwal_masuk, jadwal_pulang, toleransi_menit, keterangan, created_by, created_at)
        VALUES (:id_pegawai, :tanggal, :status_kehadiran, :id_izin,
                :jadwal_masuk, :jadwal_pulang, :toleransi_menit, :keterangan, :user, :now)
        ON CONFLICT (id_pegawai, tanggal) DO NOTHING
        RETURNING id_absensi
    """), p).scalar()


def delete_absensi_izin(conn, id_izin):
    return [r[0] for r in conn.execute(text("""
        DELETE FROM absensi WHERE id_izin = :id_izin RETURNING tanggal
    """), {"id_izin": id_izin})]


# ---------- percobaan absen (gagal) ----------

def insert_percobaan(conn, p):
    return conn.execute(text("""
        INSERT INTO percobaan_absen (id_pegawai, tipe, alasan_gagal, latitude, longitude, akurasi,
                                     jarak_meter, skor_wajah, foto_path, created_at)
        VALUES (:id_pegawai, :tipe, :alasan_gagal, :lat, :lng, :akurasi,
                :jarak_meter, :skor_wajah, :foto_path, :now)
        RETURNING id_percobaan
    """), p).scalar()


FILTER_PERCOBAAN = """WHERE (CAST(:mulai AS date) IS NULL OR x.created_at::date >= :mulai)
                        AND (CAST(:selesai AS date) IS NULL OR x.created_at::date <= :selesai)
                        AND (CAST(:id_pegawai AS int) IS NULL OR x.id_pegawai = :id_pegawai)"""


def list_percobaan(conn, f, limit, offset):
    return rows(conn.execute(text(f"""
        SELECT x.id_percobaan, x.id_pegawai, p.nama AS nama_pegawai, x.tipe, x.alasan_gagal,
               x.latitude, x.longitude, x.akurasi, x.jarak_meter, x.skor_wajah, x.foto_path, x.created_at
        FROM percobaan_absen x JOIN pegawai p ON p.id_pegawai = x.id_pegawai
        {FILTER_PERCOBAAN}
        ORDER BY x.created_at DESC
        LIMIT :limit OFFSET :offset
    """), {**f, "limit": limit, "offset": offset}))


def count_percobaan(conn, f):
    return conn.execute(text(f"SELECT count(*) FROM percobaan_absen x {FILTER_PERCOBAAN}"), f).scalar()


def get_foto_percobaan(conn, id_percobaan):
    return conn.execute(text("SELECT foto_path FROM percobaan_absen WHERE id_percobaan = :id"),
                        {"id": id_percobaan}).scalar()


# ---------- hari libur ----------

def list_hari_libur(conn, mulai, selesai):
    return rows(conn.execute(text("""
        SELECT tanggal, keterangan, created_at FROM hari_libur
        WHERE tanggal BETWEEN :mulai AND :selesai
        ORDER BY tanggal
    """), {"mulai": mulai, "selesai": selesai}))


def get_hari_libur(conn, tanggal):
    return row(conn.execute(text("""
        SELECT tanggal, keterangan, created_at FROM hari_libur WHERE tanggal = :tanggal
    """), {"tanggal": tanggal}))


def insert_hari_libur(conn, p):
    return conn.execute(text("""
        INSERT INTO hari_libur (tanggal, keterangan, created_by, created_at)
        VALUES (:tanggal, :keterangan, :user, :now)
        ON CONFLICT (tanggal) DO NOTHING
        RETURNING tanggal
    """), p).scalar()


def update_hari_libur(conn, tanggal, keterangan):
    conn.execute(text("UPDATE hari_libur SET keterangan = :keterangan WHERE tanggal = :tanggal"),
                 {"tanggal": tanggal, "keterangan": keterangan})


def delete_hari_libur(conn, tanggal):
    conn.execute(text("DELETE FROM hari_libur WHERE tanggal = :tanggal"), {"tanggal": tanggal})
