# Riwayat Perintah Pengembangan

Sesi tanggal 29 Oktober 2026 (waktu WITA). Isi tiap perintah disalin apa adanya, lalu diikuti ringkasan hasilnya.

---

## 1. Index project (09:03)
> index project ini

**Hasil:** project di-index ke graph codebase-memory.

## 2. Pegawai tanpa NIAP, akun login sekaligus, users nonaktif disembunyikan (09:09)
> saya perlu penyesuaian di module pegawai, saya tidak ingin menyimpan atau mengambil niap, karena saya tidak memerlukan niap lagi, jadi untuk sekarang kita kecualikan itu dulu baik di get terutama di post, dan di post pegawai saya ingin terintegrasi dengan users karena saat saya menambahkan pegawai saya juga menambahkan user loginnya supaya sekali jalan, dan di get users saya ingin supaya apabila ada user yang terintegrasi dengan pegawai apabila pegawainya tidak aktif dengan status = 0 maka data user itu tidak akan ditampilkan, tolong perbaiki kodenya dan tolong berikan juga perubahan dan cara menggunakannya langsung di terminal ini secara simple karena saya ingin menggunakannya sebagai transfer learning ke frontend

**Hasil:**
- NIAP dihapus dari GET, POST, dan PUT pegawai. Kolom di DB tetap ada.
- `POST /api/pegawai` menerima objek opsional `akun` (`username`, `password`, `role`, `nama`). User dibuat dalam transaksi yang sama.
- `GET /api/users` menyembunyikan user yang pegawainya berstatus 0.

## 3. Endpoint wajah pegawai dengan face recognition (09:46)
> selanjutnya saya perlu untuk menambahkan dan mengedit dan menghapus wajah pegawai yang akan disimpan nantinya, berarti kita memerlukan library face recognition untuk melakukan cropping wajah dan scale down atau kompress supaya data wajah yang kita simpan tidak terlalu besar, jadi tolong buatkan saya endpoint untuk keperluan ini

**Hasil:**
- Library dlib dipasang.
- Wajah di-crop menjadi JPEG 300x300 (sekitar 15 KB), lalu embedding 128 dimensi disimpan.

## 4. Wajah ditampilkan di GET pegawai (09:55)
> dan di get pegawai, saya ingin menambil wajahnya juga, tapi satu saja, karena saya perlu menampilkannya di frontend, tolong sesuaikan

**Hasil:** GET pegawai menyertakan field `id_wajah` dan `foto_wajah_url`.

## 5. Batas 1 wajah per pegawai (10:17)
> Saran untuk backend: batas satu foto sekarang hanya dijaga di frontend. Lewat API langsung, backend masih menerima sampai 5 foto. Agar konsisten, sebaiknya batas di backend juga diubah menjadi 1. Bila pegawai sudah punya foto, POST ditolak dengan error 409 BATAS_WAJAH, dan penggantian foto lewat PUT. Ini perubahan di backend, jadi keputusannya di Anda. saya ingin membatasi supaya di tiap pegawai hanya ada 1 wajah saja

**Hasil:** batas di backend diubah menjadi 1 wajah per pegawai.

## 6. Install dependency (10:23)
> pip install -r requirements.txt

**Hasil:** dependency terpasang dan `pip check` OK.

## 7. Modul manajemen lokasi absensi (10:25)
> dan sekarang saya membutuhkan module baru untuk lokasi absensi, karena saya ingin membuat manajement untuk lokasi absensi, tolong buatkan endpoint yang saya butuhkan untuk manajemen lokasi absensi ini

**Hasil:**
- CRUD lokasi absensi dibuat.
- Nama lokasi wajib unik.
- Penghapusan berupa soft delete, dan setiap perubahan dicatat di audit.

## 8. Refactor wajah ke modul pegawai dan lokasi ke modul sendiri (10:45)
> tolong perbaiki endpoint untuk wajah yang tidak kita perlukan karena satu pegawai hanya bisa memiliki 1 wajah, jadi tolong untuk endpoint yang kita perlukan saja yang tetap, karena multiple wajah kita tidak gunakan lagi, dan sepertinya kita memerlukan reafactor untuk wajah dan lokasi ini, saya rasa ada baiknya kita menggunakan modul baru untuk lokasi, dan untuk wajah kita masukkan ke modul pegawai supaya absensi lebih clean

**Hasil:**
- Endpoint wajah dipindah ke modul pegawai: `PUT` / `DELETE /api/pegawai/{id}/wajah` dan `GET /api/pegawai/{id}/wajah/foto`.
- Lokasi dipindah ke modul baru `/api/lokasi-absen`.
- Endpoint lama dihapus.

## 9. Wajah ditampilkan di GET users (10:55)
> di get users saya ingin menambahkan wajah pegawai apabila terintegrasi dengan pegawai namun apabila hanya pengguna dan bukan pegawai kembalikan null saja

**Hasil:**
- GET users (list dan detail) menyertakan `id_wajah` dan `foto_wajah_url`.
- Nilainya `null` untuk user yang bukan pegawai.

## 10. Modul absensi lengkap dan parser (11:03)
> sekarang buatkan endpoint absen masuk dan pulang yang disesuaikan, jadi yang disimpan tiap pegawai, absensi masuk dan pulang, serta manajemen absensi oleh admin juga serta endpoint lain yang diperlukan juga, dimana untuk pegawai hanya sedar manajemen absensi yang diperlukan dan admin juga memiliki endpoint yang diperlukan khusus admin semisal input absensi secara manual dan sebagainya, tolong berikan juga lengkapnya dan parser yang kita butuhkan

**Hasil:**
- **Pegawai:** absen masuk dan pulang dengan validasi wajah dan GPS, status hari ini, serta riwayat dan rekap bulanan.
- **Admin:** list absensi, input manual, monitor harian, rekap, koreksi, hapus, foto, percobaan gagal, dan hari libur.
- **Parser bersama:** dibuat di `app/core/params.py`.
- **Zona waktu DB:** diatur ke WITA.

## 11. Label endpoint di Swagger (11:20)
> (pegawai) Riwayat & rekap absensi saya per bulan, tolong buatkan saya indikator seperti ini di endpoint absensi swagger, supaya mudah membedakan mana endpoint yang dipakai oleh pegawai, dan mana yang dipakai oleh admin dan mana yang bisa dipakai keduanya

**Hasil:** endpoint absensi diberi label `(pegawai)`, `(admin)`, dan `(pegawai & admin)`.

## 12. Label diterapkan ke semua endpoint dan dijadikan aturan (11:22)
> iya boleh tolong lakukan labeling ke semua endpoint yang kita miliki, dan nanti terapkan rule ini apabila kita membuat endpoint baru

**Hasil:**
- Ke-54 endpoint diberi label; login berlabel `(publik)`.
- Aturan ini dicek oleh `tests/test_swagger_labels.py` dan dicatat di README.

## 13. `/effort` (14:39)
> /effort

**Hasil:** effort disetel ke low.

## 14. Login terpisah untuk aplikasi absensi (14:42)
> untuk login saya ingin menambahkan login untuk pegawai supaya ke halaman absensi, jadi karena saya mempunyai 2 frontend yang akan jalan, maka login saya ingin pisahkan namun untuk login ke aplikasi absensi bisa menggunakan username dan password dari user namun yang bisa login hanya yang terintegrasi dengan pegawai, dan diberikan pembeda nanti di jwt yang dibuatnya, jadi tolong sesuaikan endpoint yang saya butuhkan ini

**Hasil:**
- Endpoint baru `POST /api/auth/login-absensi`, hanya untuk akun yang tertaut ke pegawai aktif.
- JWT berisi klaim `app` dengan nilai `ADMIN` atau `ABSENSI`.
- Token `ABSENSI` ditolak di endpoint `(admin)`.

## 15. Riwayat perintah (15:41)
> coba tolong buatkan saya history dari perintah saya ke bentuk .md

**Hasil:** file ini.
