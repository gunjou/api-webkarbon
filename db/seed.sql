-- =====================================================================
-- Data awal. Aman dijalankan ulang (ON CONFLICT / NOT EXISTS).
-- User admin dibuat terpisah: python -m scripts.create_admin
-- =====================================================================
BEGIN;

INSERT INTO pengaturan (key, value) VALUES
('desa', '{
  "nama": "Karang Bongkot",
  "kode": "KRB",
  "kecamatan": "Labuapi",
  "kabupaten": "Lombok Barat",
  "alamat": "Jln. Gunung Pengsong No. 1 Desa Karang Bongkot Kec. Labuapi",
  "kode_pos": "83361",
  "email": "karangbongkot16@gmail.com",
  "website": "karangbongkot.desa.id",
  "logo_path": null
}'),
('format_nomor', '{"pola": "{klasifikasi}/{urut}/{kode_desa}/{tahun}", "scope": "GLOBAL"}'),
('jadwal_kerja', '{"hari_kerja": [1,2,3,4,5], "jam_masuk": "08:00", "jam_pulang": "14:00", "toleransi_menit": 15}'),
('absensi', '{"max_akurasi_meter": 50, "face_threshold": 0.5}')
ON CONFLICT (key) DO NOTHING;

COMMIT;
