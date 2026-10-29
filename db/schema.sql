-- =====================================================================
-- SISTEM KANTOR DESA - db/schema.sql
-- Modul: core, kepegawaian, kependudukan, persuratan, absensi
-- Konvensi:
--   * PK  : id_<tabel>
--   * status SMALLINT = soft delete (1 aktif, 0 dihapus) untuk data master
--   * status bisnis memakai kolom sendiri (status_surat, status_izin, ...)
--     berupa VARCHAR + CHECK (bukan ENUM Postgres, supaya mudah ditambah)
--   * semua waktu TIMESTAMPTZ, aplikasi mengirim waktu WITA (Asia/Makassar)
-- =====================================================================

BEGIN;

-- =====================================================================
-- CORE
-- =====================================================================

CREATE TABLE users (
    id_user         SERIAL PRIMARY KEY,
    username        VARCHAR(50)  NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    nama            VARCHAR(150) NOT NULL,
    role            VARCHAR(20)  NOT NULL
                    CHECK (role IN ('ADMIN', 'OPERATOR', 'PEGAWAI', 'KADES')),
    id_pegawai      INT,                         -- FK ditambahkan setelah tabel pegawai
    last_login_at   TIMESTAMPTZ,
    status          SMALLINT     NOT NULL DEFAULT 1,
    created_by      INT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_by      INT,
    updated_at      TIMESTAMPTZ
);
CREATE UNIQUE INDEX uq_users_username ON users (username) WHERE status = 1;
CREATE UNIQUE INDEX uq_users_pegawai  ON users (id_pegawai) WHERE status = 1 AND id_pegawai IS NOT NULL;

-- Key-value konfigurasi. Contoh key & isi value:
--   'desa'         {"nama":"Karang Bongkot","kode":"KRB","kecamatan":"Labuapi",
--                   "kabupaten":"Lombok Barat","alamat":"Jln. Gunung Pengsong No. 1",
--                   "kode_pos":"83361","email":"...","website":"...","logo_path":"..."}
--   'format_nomor' {"pola":"{klasifikasi}/{urut}/{kode_desa}/{tahun}","scope":"GLOBAL"}
--   'jadwal_kerja' {"hari_kerja":[1,2,3,4,5],"jam_masuk":"08:00","jam_pulang":"14:00",
--                   "toleransi_menit":15}
--   'absensi'      {"max_akurasi_meter":50,"face_threshold":0.5}
CREATE TABLE pengaturan (
    key             VARCHAR(50) PRIMARY KEY,
    value           JSONB       NOT NULL,
    updated_by      INT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit_log (
    id_audit        BIGSERIAL PRIMARY KEY,
    id_user         INT,
    aksi            VARCHAR(50) NOT NULL,        -- 'KOREKSI_ABSENSI', 'BATAL_SURAT', ...
    entitas         VARCHAR(50) NOT NULL,        -- nama tabel
    id_entitas      BIGINT,
    data_lama       JSONB,
    data_baru       JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_entitas ON audit_log (entitas, id_entitas);

-- =====================================================================
-- KEPEGAWAIAN (shared: absensi, penandatangan surat, payroll nanti)
-- =====================================================================

CREATE TABLE pegawai (
    id_pegawai      SERIAL PRIMARY KEY,
    nama            VARCHAR(150) NOT NULL,
    nik             CHAR(16),
    niap            VARCHAR(30),
    jabatan         VARCHAR(100) NOT NULL,       -- 'Kepala Desa', 'Sekretaris Desa', 'Kadus ...'
    no_hp           VARCHAR(20),
    tanggal_mulai   DATE,
    status          SMALLINT     NOT NULL DEFAULT 1,
    created_by      INT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_by      INT,
    updated_at      TIMESTAMPTZ
);

ALTER TABLE users
    ADD CONSTRAINT fk_users_pegawai FOREIGN KEY (id_pegawai) REFERENCES pegawai (id_pegawai);

-- =====================================================================
-- KEPENDUDUKAN (shared)
-- =====================================================================

CREATE TABLE penduduk (
    id_penduduk     SERIAL PRIMARY KEY,
    nik             CHAR(16)     NOT NULL,
    no_kk           CHAR(16),
    nama            VARCHAR(150) NOT NULL,
    tempat_lahir    VARCHAR(100),
    tgl_lahir       DATE,
    jenis_kelamin   CHAR(1)      CHECK (jenis_kelamin IN ('L', 'P')),
    agama           VARCHAR(30),
    status_kawin    VARCHAR(30),
    pekerjaan       VARCHAR(100),
    kewarganegaraan VARCHAR(50)  NOT NULL DEFAULT 'Indonesia',
    alamat          TEXT,                        -- jalan / detail tambahan (opsional)
    dusun           VARCHAR(100),
    rt              VARCHAR(5),
    rw              VARCHAR(5),
    status          SMALLINT     NOT NULL DEFAULT 1,
    created_by      INT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_by      INT,
    updated_at      TIMESTAMPTZ
);
CREATE UNIQUE INDEX uq_penduduk_nik ON penduduk (nik) WHERE status = 1;
CREATE INDEX idx_penduduk_nama ON penduduk (lower(nama));
CREATE INDEX idx_penduduk_kk   ON penduduk (no_kk);

-- =====================================================================
-- PERSURATAN
-- =====================================================================

CREATE TABLE jenis_surat (
    id_jenis_surat   SERIAL PRIMARY KEY,
    kode             VARCHAR(30)  NOT NULL,      -- 'SK_BELUM_MENIKAH', 'UMUM'
    nama             VARCHAR(150) NOT NULL,      -- nama di menu
    judul_surat      VARCHAR(200) NOT NULL,      -- judul tercetak: 'SURAT KETERANGAN BELUM MENIKAH'
    kode_klasifikasi VARCHAR(20)  NOT NULL,      -- '148.1'
    pakai_subjek     BOOLEAN      NOT NULL DEFAULT TRUE,
    field_schema     JSONB        NOT NULL DEFAULT '[]',
    template_isi     TEXT         NOT NULL,      -- Jinja (dirender sandbox)
    urutan           INT          NOT NULL DEFAULT 0,
    status           SMALLINT     NOT NULL DEFAULT 1,
    created_by       INT,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_by       INT,
    updated_at       TIMESTAMPTZ
);
CREATE UNIQUE INDEX uq_jenis_surat_kode ON jenis_surat (kode) WHERE status = 1;

CREATE TABLE penandatangan (
    id_penandatangan SERIAL PRIMARY KEY,
    id_pegawai       INT          NOT NULL REFERENCES pegawai (id_pegawai),
    jabatan_label    VARCHAR(100) NOT NULL,      -- 'Sekretaris Desa'
    mode             VARCHAR(10)  NOT NULL CHECK (mode IN ('LANGSUNG', 'AN')),
    is_default       BOOLEAN      NOT NULL DEFAULT FALSE,
    status           SMALLINT     NOT NULL DEFAULT 1,
    created_by       INT,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_by       INT,
    updated_at       TIMESTAMPTZ
);

-- Satu baris per (scope, tahun). scope 'GLOBAL' = satu nomor agenda untuk semua surat.
-- Kalau nanti per klasifikasi, scope diisi kode_klasifikasi, tanpa ubah skema.
CREATE TABLE nomor_counter (
    scope           VARCHAR(30) NOT NULL,
    tahun           INT         NOT NULL,
    last_number     INT         NOT NULL DEFAULT 0,
    PRIMARY KEY (scope, tahun)
);

-- data JSONB:
--   {"subjek":   {"nik","nama","tempat_lahir","tgl_lahir","jenis_kelamin","agama",
--                 "status_kawin","pekerjaan","kewarganegaraan","alamat_lengkap", ...},
--    "keperluan": "...",
--    "isian":     {...field khusus sesuai field_schema...}}
-- penandatangan JSONB (snapshot saat final):
--   {"id_penandatangan":2,"nama":"KAHARUDIN","jabatan":"Sekretaris Desa","mode":"AN"}
CREATE TABLE surat (
    id_surat         BIGSERIAL PRIMARY KEY,
    id_jenis_surat   INT          NOT NULL REFERENCES jenis_surat (id_jenis_surat),
    status_surat     VARCHAR(10)  NOT NULL DEFAULT 'DRAFT'
                     CHECK (status_surat IN ('DRAFT', 'FINAL', 'BATAL')),
    id_penduduk      INT          REFERENCES penduduk (id_penduduk),  -- NULL = belum terdaftar
    data             JSONB        NOT NULL,
    id_penandatangan INT          REFERENCES penandatangan (id_penandatangan),
    penandatangan    JSONB,
    nomor_urut       INT,
    nomor_surat      VARCHAR(100),
    tanggal_surat    DATE,
    file_pdf         VARCHAR(255),
    alasan_batal     TEXT,
    created_by       INT          NOT NULL,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_by       INT,
    updated_at       TIMESTAMPTZ,
    finalized_by     INT,
    finalized_at     TIMESTAMPTZ,
    dibatalkan_by    INT,
    dibatalkan_at    TIMESTAMPTZ,
    CONSTRAINT ck_surat_final_bernomor
        CHECK (status_surat = 'DRAFT' OR (nomor_surat IS NOT NULL AND tanggal_surat IS NOT NULL))
);
CREATE UNIQUE INDEX uq_surat_nomor  ON surat (nomor_surat) WHERE nomor_surat IS NOT NULL;
CREATE INDEX idx_surat_register     ON surat (id_jenis_surat, tanggal_surat);
CREATE INDEX idx_surat_status       ON surat (status_surat);
CREATE INDEX idx_surat_penduduk     ON surat (id_penduduk);
CREATE INDEX idx_surat_nik          ON surat ((data->'subjek'->>'nik'));

-- =====================================================================
-- ABSENSI
-- =====================================================================

CREATE TABLE lokasi_absen (
    id_lokasi       SERIAL PRIMARY KEY,
    nama            VARCHAR(100)  NOT NULL,
    latitude        NUMERIC(10,7) NOT NULL,
    longitude       NUMERIC(10,7) NOT NULL,
    radius_meter    INT           NOT NULL DEFAULT 100,
    status          SMALLINT      NOT NULL DEFAULT 1,
    created_by      INT,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_by      INT,
    updated_at      TIMESTAMPTZ
);

CREATE TABLE wajah_pegawai (
    id_wajah        SERIAL PRIMARY KEY,
    id_pegawai      INT          NOT NULL REFERENCES pegawai (id_pegawai),
    embedding       FLOAT8[]     NOT NULL,
    foto_path       VARCHAR(255) NOT NULL,
    status          SMALLINT     NOT NULL DEFAULT 1,
    created_by      INT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_wajah_pegawai ON wajah_pegawai (id_pegawai) WHERE status = 1;

CREATE TABLE hari_libur (
    tanggal         DATE PRIMARY KEY,
    keterangan      VARCHAR(150) NOT NULL,
    created_by      INT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE izin (
    id_izin         SERIAL PRIMARY KEY,
    id_pegawai      INT          NOT NULL REFERENCES pegawai (id_pegawai),
    jenis           VARCHAR(10)  NOT NULL CHECK (jenis IN ('IZIN', 'SAKIT', 'CUTI', 'DINAS')),
    tanggal_mulai   DATE         NOT NULL,
    tanggal_selesai DATE         NOT NULL,
    alasan          TEXT         NOT NULL,
    lampiran        VARCHAR(255),
    status_izin     VARCHAR(12)  NOT NULL DEFAULT 'PENDING'
                    CHECK (status_izin IN ('PENDING', 'DISETUJUI', 'DITOLAK', 'DIBATALKAN')),
    catatan_proses  TEXT,
    diproses_by     INT,
    diproses_at     TIMESTAMPTZ,
    created_by      INT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_by      INT,
    updated_at      TIMESTAMPTZ,
    CONSTRAINT ck_izin_tanggal CHECK (tanggal_selesai >= tanggal_mulai)
);
CREATE INDEX idx_izin_pegawai ON izin (id_pegawai, tanggal_mulai);

-- Satu baris = satu pegawai satu hari. Sumber kebenaran harian:
--   HADIR      : dari check-in
--   IZIN/SAKIT/CUTI/DINAS : dibuat otomatis saat izin DISETUJUI (id_izin terisi)
-- Hari kerja tanpa baris = alpha (dihitung saat rekap, tanpa cron).
CREATE TABLE absensi (
    id_absensi         BIGSERIAL PRIMARY KEY,
    id_pegawai         INT          NOT NULL REFERENCES pegawai (id_pegawai),
    tanggal            DATE         NOT NULL,
    status_kehadiran   VARCHAR(10)  NOT NULL DEFAULT 'HADIR'
                       CHECK (status_kehadiran IN ('HADIR', 'IZIN', 'SAKIT', 'CUTI', 'DINAS')),
    id_izin            INT          REFERENCES izin (id_izin),

    -- snapshot jadwal hari itu
    jadwal_masuk       TIME,
    jadwal_pulang      TIME,
    toleransi_menit    INT,

    jam_masuk          TIMESTAMPTZ,
    lat_masuk          NUMERIC(10,7),
    lng_masuk          NUMERIC(10,7),
    akurasi_masuk      REAL,
    id_lokasi_masuk    INT          REFERENCES lokasi_absen (id_lokasi),
    foto_masuk         VARCHAR(255),
    skor_masuk         REAL,

    jam_pulang         TIMESTAMPTZ,
    lat_pulang         NUMERIC(10,7),
    lng_pulang         NUMERIC(10,7),
    akurasi_pulang     REAL,
    id_lokasi_pulang   INT          REFERENCES lokasi_absen (id_lokasi),
    foto_pulang        VARCHAR(255),
    skor_pulang        REAL,

    menit_telat        INT          NOT NULL DEFAULT 0,
    menit_pulang_cepat INT          NOT NULL DEFAULT 0,
    keterangan         TEXT,
    is_koreksi         BOOLEAN      NOT NULL DEFAULT FALSE,

    created_by         INT,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_by         INT,
    updated_at         TIMESTAMPTZ,
    CONSTRAINT uq_absensi_harian UNIQUE (id_pegawai, tanggal)
);
CREATE INDEX idx_absensi_tanggal ON absensi (tanggal);

-- Log absen yang DITOLAK (untuk komplain & audit kecurangan)
CREATE TABLE percobaan_absen (
    id_percobaan    BIGSERIAL PRIMARY KEY,
    id_pegawai      INT          NOT NULL REFERENCES pegawai (id_pegawai),
    tipe            VARCHAR(6)   NOT NULL CHECK (tipe IN ('MASUK', 'PULANG')),
    alasan_gagal    VARCHAR(30)  NOT NULL,       -- 'DI_LUAR_RADIUS', 'WAJAH_TIDAK_COCOK', ...
    latitude        NUMERIC(10,7),
    longitude       NUMERIC(10,7),
    akurasi         REAL,
    jarak_meter     REAL,
    skor_wajah      REAL,
    foto_path       VARCHAR(255),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_percobaan_pegawai ON percobaan_absen (id_pegawai, created_at);

COMMIT;
