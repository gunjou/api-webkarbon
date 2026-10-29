# Sistem Absensi – Backend

## Stack

Flask, flask_restx, PostgreSQL (TZ: Asia/Makassar/WITA), dlib untuk wajah.

## Struktur

- app/modules/<nama>/ → routes, service, queries per modul; daftarkan di app/modules/__init__.py
- app/core/params.py → parser bersama (pakai ini, jangan buat baru)

## Aturan wajib

- Setiap endpoint diberi label di summary: (publik)/(pegawai)/(admin)/(pegawai & admin).
  Dicek oleh tests/test_swagger_labels.py
- Hapus data = soft delete + catat audit
- Error bisnis: kode HTTP + kode string, contoh 409 BATAS_WAJAH
- Password minimal 5 karakter (buat user, reset, ganti password)

## Keputusan domain

- NIAP tidak dipakai (kolom DB tetap ada, jangan diakses)
- 1 pegawai = 1 wajah (JPEG 300x300 + embedding 128-d)
- JWT berisi klaim `app`: ADMIN | ABSENSI. Token ABSENSI ditolak di endpoint (admin)
- Token lama tanpa klaim `app` dianggap ADMIN; login-absensi hanya untuk user yang tertaut ke pegawai aktif
- User yang pegawainya status=0 disembunyikan dari GET users
- Wajah ada di modul kepegawaian, lokasi di modul lokasi_absen; antarmodul lewat service, bukan query
- Validasi absen: wajah terdaftar → hari kerja → belum absen → akurasi GPS → radius → wajah cocok; gagal dicatat ke percobaan_absen
- Data pegawai sendiri diambil dari token (current_pegawai_id), mis. GET /pegawai/me; bukan dari id di URL
- Perizinan (IZIN/SAKIT/CUTI/DINAS): PENDING → DISETUJUI/DITOLAK/DIBATALKAN. Disetujui → baris absensi per hari kerja (id_izin terisi); dibatalkan admin → baris itu dihapus
- Setujui/tolak izin: ADMIN & KADES. SAKIT wajib lampiran; maks 90 hari; tanggal bentrok → 409 IZIN_BENTROK

## Cara kerja

- Gunakan codebase-memory untuk cari simbol sebelum membaca file utuh
- Jangan jalankan `npm run gen:api` (frontend) kecuali diminta
- Jawaban ringkas: diff singkat + 1 contoh request/response, tanpa penjelasan panjang
