# Dokumentasi Endpoint API Sistem Kantor Desa

Dokumen ini merangkum semua endpoint yang **sudah tersedia**, lengkap dengan role, parameter,
contoh request, dan contoh response. Untuk mencoba langsung, buka Swagger UI di `/docs`.

## Daftar isi

- [Informasi umum](#informasi-umum)
  - [Base URL](#base-url)
  - [Autentikasi](#autentikasi)
  - [Format response](#format-response)
  - [Kode status & error umum](#kode-status--error-umum)
  - [Role](#role)
- [Auth](#auth) — login, data akun, ganti password
- [Admin](#admin) — manajemen user / admin
- [Pengaturan](#pengaturan) — konfigurasi desa
- [Pegawai](#pegawai) — data perangkat desa
- [Penduduk](#penduduk) — master data penduduk
- [Persuratan](#persuratan) — jenis surat, penandatangan, draft surat
- [Lokasi Absen](#lokasi-absen) — titik & radius geofence
- [Absensi](#absensi) — absen masuk/pulang, monitor, manajemen, rekap, hari libur
- [Ringkasan semua endpoint](#ringkasan-semua-endpoint)
- [Endpoint yang direncanakan](#endpoint-yang-direncanakan)

---

## Informasi umum

### Base URL

| Lingkungan | Base URL API | Swagger UI |
|---|---|---|
| Development (`python wsgi.py`) | `http://localhost:5001/api` | `http://localhost:5001/docs` |
| Produksi (`gunicorn -c gunicorn.conf.py wsgi:app`) | `http://<server>:5000/api` | `http://<server>:5000/docs` |

Spesifikasi OpenAPI (Swagger 2.0): `GET /api/swagger.json`.
Health check (tanpa token): `GET /health` → `{"status": "ok"}`.

Contoh di dokumen ini memakai:

```bash
BASE=http://localhost:5001/api
TOKEN=<access_token dari /auth/login>
```

### Autentikasi

Semua endpoint, **kecuali `POST /auth/login`**, wajib membawa JWT di header:

```
Authorization: Bearer <access_token>
```

Alur:

1. `POST /auth/login` dengan username & password → dapat `access_token`.
2. Kirim token di header `Authorization` untuk request berikutnya.
3. Token berlaku **12 jam** (bisa diatur lewat `JWT_EXPIRES_HOURS` di `.env`). Setelah kedaluwarsa, login ulang.

Di Swagger UI: klik tombol **Authorize**, lalu isi `Bearer <access_token>` (dengan kata `Bearer`).

Token berisi klaim `role` dan `id_pegawai`; hak akses setiap endpoint dicek dari `role`.

### Format response

**Sukses** — selalu dibungkus `data`:

```json
{ "data": { ... } }
```

**List dengan paginasi** (`/penduduk`, `/persuratan/surat`):

```json
{
  "data": {
    "items": [ ... ],
    "total": 120,
    "page": 1,
    "per_page": 20
  }
}
```

`page` minimal 1, `per_page` antara 1–100 (nilai di luar rentang otomatis disesuaikan).

**Error** — satu format untuk seluruh API:

```json
{
  "error": {
    "code": "FIELD_WAJIB_KOSONG",
    "message": "Field wajib belum diisi: nama",
    "details": { "fields": ["nama"] }
  }
}
```

- `code` stabil dan aman dipakai frontend untuk logika (mis. menampilkan pesan khusus).
- `message` berbahasa Indonesia, siap ditampilkan ke pengguna.
- `details` opsional (tidak selalu ada).

> Pengecualian: endpoint dengan validasi otomatis (`POST /auth/login`, `POST /auth/ganti-password`)
> mengembalikan format bawaan flask-restx bila field wajib tidak dikirim:
> `{"errors": {"username": "'username' is a required property"}, "message": "Input payload validation failed"}` (400).

**Format tanggal & waktu:** tanggal `YYYY-MM-DD` (mis. `1990-05-17`), waktu ISO 8601 dengan
zona WITA (mis. `2026-10-27T09:15:00+08:00`).

### Kode status & error umum

| Status | Arti | Contoh `code` |
|---|---|---|
| 200 | Berhasil | — |
| 201 | Data baru dibuat | — |
| 400 | Input tidak valid / field wajib kosong | `FIELD_WAJIB_KOSONG`, `NIK_TIDAK_VALID` |
| 401 | Belum login / token salah / token kedaluwarsa | `TOKEN_TIDAK_ADA`, `TOKEN_TIDAK_VALID`, `TOKEN_KEDALUWARSA`, `LOGIN_GAGAL` |
| 403 | Role tidak punya akses | `AKSES_DITOLAK` |
| 404 | Data tidak ditemukan | `PEGAWAI_TIDAK_DITEMUKAN`, `SURAT_TIDAK_DITEMUKAN` |
| 409 | Konflik dengan data yang sudah ada | `NIK_SUDAH_TERDAFTAR`, `USERNAME_SUDAH_DIPAKAI`, `DATA_KONFLIK` |
| 500 | Kesalahan server / database | `DATABASE_ERROR`, `INTERNAL_ERROR` |

Error 401/403/500 di atas bisa muncul di endpoint mana pun yang butuh token, jadi tidak diulang
di setiap endpoint di bawah.

### Role

| Role | Keterangan |
|---|---|
| `ADMIN` | Akses penuh, termasuk manajemen user, hapus data, dan pengaturan |
| `OPERATOR` | Input data penduduk dan surat |
| `KADES` | Kepala desa: melihat data (read-only) |
| `PEGAWAI` | Pegawai desa (untuk fitur absensi yang akan datang); wajib tertaut ke data pegawai |

Hapus data di seluruh API bersifat **soft delete**: data ditandai tidak aktif, tidak benar-benar
dihapus dari database. Perubahan dan penghapusan penting dicatat di `audit_log`.

---

## Auth

### POST `/auth/login` — Login

Tanpa token.

**Body**

| Field | Tipe | Wajib | Keterangan |
|---|---|---|---|
| `username` | string | ya | |
| `password` | string | ya | |

```bash
curl -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "rahasia123"}'
```

**Response 200**

```json
{
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "user": {
      "id_user": 1,
      "username": "admin",
      "nama": "Administrator",
      "role": "ADMIN",
      "id_pegawai": null
    }
  }
}
```

**Error:** `LOGIN_GAGAL` (401) bila username tidak ada / password salah.

---

### POST `/auth/login-absensi` — Login aplikasi absensi pegawai

Tanpa token. Body sama dengan `/auth/login`. Hanya akun yang **tertaut ke pegawai aktif** yang bisa login.

**Klaim `app` di JWT** membedakan asal token:

| Login | `app` | Bisa dipakai untuk |
|---|---|---|
| `POST /auth/login` | `ADMIN` | semua endpoint sesuai role |
| `POST /auth/login-absensi` | `ABSENSI` | endpoint (pegawai) & (pegawai & admin); endpoint (admin) ditolak 403 `AKSES_DITOLAK` |

**Response 200**

```json
{
  "data": {
    "access_token": "eyJ...", "app": "ABSENSI",
    "user": { "id_user": 5, "username": "kaharudin", "nama": "Kaharudin", "role": "PEGAWAI", "id_pegawai": 2 },
    "pegawai": { "id_pegawai": 2, "nama": "Kaharudin", "jabatan": "Sekretaris Desa",
                 "id_wajah": 7, "foto_wajah_url": "/api/pegawai/2/wajah/foto?v=7" }
  }
}
```

**Error:** `LOGIN_GAGAL` (401), `BUKAN_PEGAWAI` (403, akun tidak tertaut pegawai aktif).

---

### GET `/auth/me` — Data akun yang sedang login

Role: semua user yang login.

```bash
curl $BASE/auth/me -H "Authorization: Bearer $TOKEN"
```

**Response 200**

```json
{
  "data": {
    "id_user": 1,
    "username": "admin",
    "nama": "Administrator",
    "role": "ADMIN",
    "id_pegawai": null
  }
}
```

**Error:** `USER_TIDAK_DITEMUKAN` (404) bila akun sudah dihapus.

---

### POST `/auth/ganti-password` — Ganti password sendiri

Role: semua user yang login.

**Body**

| Field | Tipe | Wajib | Keterangan |
|---|---|---|---|
| `password_lama` | string | ya | |
| `password_baru` | string | ya | Minimal 8 karakter |

```bash
curl -X POST $BASE/auth/ganti-password \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"password_lama": "rahasia123", "password_baru": "rahasiaBaru456"}'
```

**Response 200**

```json
{ "data": { "message": "Password berhasil diubah" } }
```

**Error:** `PASSWORD_TERLALU_PENDEK` (400), `PASSWORD_LAMA_SALAH` (400).

---

## Admin

Manajemen akun user untuk semua role. Semua endpoint: **role ADMIN**.

> **Membuat admin pertama** (tabel `users` masih kosong): comment `@roles_required(ADMIN)` di atas
> method `post` pada `app/modules/admin/routes.py`, panggil `POST /admin/users` tanpa token,
> lalu aktifkan kembali baris tersebut. Alternatif tanpa ubah kode: `python -m scripts.create_admin`.

**Objek user (response)**

| Field | Tipe | Keterangan |
|---|---|---|
| `id_user` | integer | |
| `username` | string | |
| `nama` | string | |
| `role` | string | `ADMIN` / `OPERATOR` / `PEGAWAI` / `KADES` |
| `id_pegawai` | integer \| null | Pegawai yang tertaut |
| `nama_pegawai` | string \| null | Nama pegawai yang tertaut |
| `id_wajah` | integer \| null | Wajah pegawai tertaut; `null` kalau bukan pegawai / belum punya wajah |
| `foto_wajah_url` | string \| null | mis. `/api/pegawai/2/wajah/foto?v=7` (GET dengan header Authorization); `null` kalau bukan pegawai / belum punya wajah |
| `last_login_at` | datetime \| null | |
| `created_at` | datetime | |
| `updated_at` | datetime \| null | |

`password_hash` tidak pernah dikembalikan.

### GET `/admin/users` — Daftar user

User yang tertaut ke pegawai nonaktif (pegawai `status = 0` / sudah dihapus) tidak ditampilkan.

**Query**

| Param | Keterangan |
|---|---|
| `q` | Cari username / nama (sebagian) |
| `role` | Filter role: `ADMIN`, `OPERATOR`, `PEGAWAI`, `KADES` |

```bash
curl "$BASE/admin/users?role=OPERATOR&q=budi" -H "Authorization: Bearer $TOKEN"
```

**Response 200**

```json
{
  "data": [
    {
      "id_user": 2,
      "username": "budi",
      "nama": "Budi Santoso",
      "role": "OPERATOR",
      "id_pegawai": 3,
      "nama_pegawai": "Budi Santoso",
      "last_login_at": "2026-10-27T08:01:12+08:00",
      "created_at": "2026-10-20T10:00:00+08:00",
      "updated_at": null
    }
  ]
}
```

---

### POST `/admin/users` — Buat user / admin baru

**Body**

| Field | Tipe | Wajib | Keterangan |
|---|---|---|---|
| `username` | string | ya | 3–50 karakter: huruf, angka, titik, underscore. Unik |
| `nama` | string | ya | |
| `password` | string | ya | Minimal 5 karakter |
| `role` | string | tidak | Default `ADMIN` |
| `id_pegawai` | integer | tidak* | *Wajib bila `role` = `PEGAWAI`. Satu pegawai hanya boleh satu akun |

```bash
curl -X POST $BASE/admin/users \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"username": "budi", "nama": "Budi Santoso", "password": "rahasia123", "role": "OPERATOR"}'
```

**Response 201** — objek user (lihat di atas) dalam `data`.

**Error:** `FIELD_WAJIB_KOSONG`, `USERNAME_TIDAK_VALID`, `ROLE_TIDAK_VALID`,
`PASSWORD_TERLALU_PENDEK`, `PEGAWAI_WAJIB_DIISI` (400); `PEGAWAI_TIDAK_DITEMUKAN` (404);
`USERNAME_SUDAH_DIPAKAI`, `PEGAWAI_SUDAH_PUNYA_AKUN` (409).

---

### GET `/admin/users/{id_user}` — Detail user

```bash
curl $BASE/admin/users/2 -H "Authorization: Bearer $TOKEN"
```

**Response 200** — objek user dalam `data`. **Error:** `USER_TIDAK_DITEMUKAN` (404).

---

### PUT `/admin/users/{id_user}` — Ubah data user

Mengubah username, nama, role, dan tautan pegawai. **Password tidak diubah di sini** (pakai reset-password).
Body sama seperti `POST /admin/users` tanpa `password`; semua field dikirim ulang (bukan sebagian).

```bash
curl -X PUT $BASE/admin/users/2 \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"username": "budi", "nama": "Budi Santoso", "role": "PEGAWAI", "id_pegawai": 3}'
```

**Response 200** — objek user terbaru dalam `data`.

**Error:** sama seperti POST, ditambah `USER_TIDAK_DITEMUKAN` (404) dan `ADMIN_TERAKHIR` (409)
bila mencoba menurunkan role satu-satunya admin aktif.

---

### PUT `/admin/users/{id_user}/reset-password` — Reset password user

Tidak perlu password lama.

**Body**

| Field | Tipe | Wajib | Keterangan |
|---|---|---|---|
| `password_baru` | string | ya | Minimal 5 karakter |

```bash
curl -X PUT $BASE/admin/users/2/reset-password \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"password_baru": "passwordBaru1"}'
```

**Response 200**

```json
{ "data": { "message": "Password berhasil direset" } }
```

**Error:** `PASSWORD_TERLALU_PENDEK` (400), `USER_TIDAK_DITEMUKAN` (404).

---

### DELETE `/admin/users/{id_user}` — Hapus user

```bash
curl -X DELETE $BASE/admin/users/2 -H "Authorization: Bearer $TOKEN"
```

**Response 200**

```json
{ "data": { "message": "User dihapus" } }
```

**Error:** `USER_TIDAK_DITEMUKAN` (404); `HAPUS_DIRI_SENDIRI` (409) bila menghapus akun sendiri;
`ADMIN_TERAKHIR` (409) bila menghapus satu-satunya admin aktif.

---

## Pengaturan

Konfigurasi desa disimpan sebagai pasangan key → nilai JSON bebas.

Key yang dipakai sistem:

| Key | Contoh `value` |
|---|---|
| `desa` | `{"nama": "Karang Bongkot", "kode": "KRB", "kecamatan": "Labuapi", "kabupaten": "Lombok Barat", "alamat": "...", "kode_pos": "83361", "email": "...", "website": "...", "logo_path": null}` |
| `format_nomor` | `{"pola": "{klasifikasi}/{urut}/{kode_desa}/{tahun}", "scope": "GLOBAL"}` |
| `jadwal_kerja` | `{"hari_kerja": [1,2,3,4,5], "jam_masuk": "08:00", "jam_pulang": "14:00", "toleransi_menit": 15}` |
| `absensi` | `{"max_akurasi_meter": 50, "face_threshold": 0.5}` |

### GET `/pengaturan` — Semua pengaturan

Role: ADMIN, OPERATOR, KADES.

```bash
curl $BASE/pengaturan -H "Authorization: Bearer $TOKEN"
```

**Response 200**

```json
{
  "data": [
    {
      "key": "desa",
      "value": { "nama": "Karang Bongkot", "kode": "KRB", "kecamatan": "Labuapi" },
      "updated_by": 1,
      "updated_at": "2026-10-20T10:00:00+08:00"
    }
  ]
}
```

---

### GET `/pengaturan/{key}` — Ambil satu pengaturan

Role: semua user yang login.

```bash
curl $BASE/pengaturan/desa -H "Authorization: Bearer $TOKEN"
```

**Response 200**

```json
{ "data": { "key": "desa", "value": { "nama": "Karang Bongkot", "kode": "KRB" } } }
```

**Error:** `PENGATURAN_TIDAK_DITEMUKAN` (404).

---

### PUT `/pengaturan/{key}` — Simpan pengaturan

Role: ADMIN. Membuat key baru atau **menimpa seluruh** nilai key yang sudah ada (bukan merge),
jadi kirim objek lengkap. Dicatat di audit log.

**Body**

| Field | Tipe | Wajib | Keterangan |
|---|---|---|---|
| `value` | JSON apa saja | ya | Object, array, string, atau angka |

```bash
curl -X PUT $BASE/pengaturan/jadwal_kerja \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"value": {"hari_kerja": [1,2,3,4,5], "jam_masuk": "07:30", "jam_pulang": "14:00", "toleransi_menit": 10}}'
```

**Response 200**

```json
{ "data": { "key": "jadwal_kerja", "value": { "hari_kerja": [1,2,3,4,5], "jam_masuk": "07:30", "jam_pulang": "14:00", "toleransi_menit": 10 } } }
```

**Error:** `FIELD_WAJIB_KOSONG` (400) bila `value` tidak dikirim.

---

## Pegawai

**Objek pegawai (response)**

| Field | Tipe | Keterangan |
|---|---|---|
| `id_pegawai` | integer | |
| `nama` | string | |
| `jabatan` | string | mis. `Sekretaris Desa` |
| `nik` | string \| null | |
| `no_hp` | string \| null | |
| `tanggal_mulai` | date \| null | |
| `created_at` | datetime | |
| `updated_at` | datetime \| null | |
| `id_wajah` | integer \| null | foto wajah aktif; `null` kalau belum ada |
| `foto_wajah_url` | string \| null | mis. `/api/pegawai/2/wajah/foto?v=7`, `GET` dengan header Authorization |

### GET `/pegawai` — Daftar pegawai

Role: ADMIN, OPERATOR, KADES. Tanpa paginasi, urut nama.

| Query | Keterangan |
|---|---|
| `q` | Cari nama / jabatan (sebagian) |

```bash
curl "$BASE/pegawai?q=sekretaris" -H "Authorization: Bearer $TOKEN"
```

**Response 200**

```json
{
  "data": [
    {
      "id_pegawai": 2,
      "nama": "Kaharudin",
      "jabatan": "Sekretaris Desa",
      "nik": "5201xxxxxxxxxxxx",
      "no_hp": "081234567890",
      "tanggal_mulai": "2020-01-02",
      "created_at": "2026-10-20T10:00:00+08:00",
      "updated_at": null,
      "id_wajah": 7,
      "foto_wajah_url": "/api/pegawai/2/wajah/foto?v=7"
    }
  ]
}
```

---

### POST `/pegawai` — Tambah pegawai (opsional sekaligus user login)

Role: ADMIN. Kalau `akun` diisi, pegawai dan user login dibuat dalam satu transaksi —
kalau pembuatan akun gagal (mis. username dipakai), pegawai juga batal dibuat.

**Body**

| Field | Tipe | Wajib |
|---|---|---|
| `nama` | string | ya |
| `jabatan` | string | ya |
| `nik` | string | tidak |
| `no_hp` | string | tidak |
| `tanggal_mulai` | date (`YYYY-MM-DD`) | tidak |
| `akun` | object | tidak |
| `akun.username` | string (3-50: huruf, angka, `.`, `_`) | ya, jika `akun` diisi |
| `akun.password` | string (min. 5) | ya, jika `akun` diisi |
| `akun.role` | `ADMIN` \| `OPERATOR` \| `PEGAWAI` \| `KADES` | tidak (default `PEGAWAI`) |
| `akun.nama` | string | tidak (default nama pegawai) |

```bash
curl -X POST $BASE/pegawai \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"nama": "Kaharudin", "jabatan": "Sekretaris Desa", "no_hp": "081234567890",
       "akun": {"username": "kaharudin", "password": "rahasia123"}}'
```

**Response 201** — objek pegawai + `akun` (objek user, atau `null` kalau `akun` tidak dikirim).

```json
{
  "data": {
    "id_pegawai": 2, "nama": "Kaharudin", "jabatan": "Sekretaris Desa", "nik": null,
    "no_hp": "081234567890", "tanggal_mulai": null,
    "created_at": "2026-10-29T09:00:00+08:00", "updated_at": null,
    "akun": {"id_user": 5, "username": "kaharudin", "nama": "Kaharudin", "role": "PEGAWAI",
             "id_pegawai": 2, "nama_pegawai": "Kaharudin", "last_login_at": null,
             "created_at": "2026-10-29T09:00:00+08:00", "updated_at": null}
  }
}
```

**Error:** `FIELD_WAJIB_KOSONG`, `AKUN_TIDAK_VALID`, `USERNAME_TIDAK_VALID`, `ROLE_TIDAK_VALID`,
`PASSWORD_TERLALU_PENDEK` (400), `USERNAME_SUDAH_DIPAKAI` (409).

---

### GET `/pegawai/{id_pegawai}` — Detail pegawai

Role: ADMIN, OPERATOR, KADES.

```bash
curl $BASE/pegawai/2 -H "Authorization: Bearer $TOKEN"
```

**Response 200** — objek pegawai dalam `data`. **Error:** `PEGAWAI_TIDAK_DITEMUKAN` (404).

---

### PUT `/pegawai/{id_pegawai}` — Ubah pegawai

Role: ADMIN. Body sama seperti POST; semua field dikirim ulang (field yang tidak dikirim menjadi kosong).
Dicatat di audit log.

```bash
curl -X PUT $BASE/pegawai/2 \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"nama": "Kaharudin", "jabatan": "Sekretaris Desa", "no_hp": "081299999999", "tanggal_mulai": "2020-01-02"}'
```

**Response 200** — objek pegawai terbaru. **Error:** `FIELD_WAJIB_KOSONG` (400), `PEGAWAI_TIDAK_DITEMUKAN` (404).

---

### DELETE `/pegawai/{id_pegawai}` — Hapus pegawai

Role: ADMIN. Dicatat di audit log.

```bash
curl -X DELETE $BASE/pegawai/2 -H "Authorization: Bearer $TOKEN"
```

**Response 200**

```json
{ "data": { "message": "Pegawai dihapus" } }
```

**Error:** `PEGAWAI_TIDAK_DITEMUKAN` (404).

---

### PUT `/pegawai/{id_pegawai}/wajah` — Simpan wajah pegawai (tambah / ganti)

Role: ADMIN. `multipart/form-data`, field `foto` (JPG/PNG, tepat satu wajah).
Satu pegawai hanya punya **1 wajah**: kalau belum ada -> ditambahkan (**201**), kalau sudah ada -> diganti (**200**).
Server mendeteksi wajah, menyimpan embedding (untuk verifikasi absen), lalu menyimpan crop wajah
300x300 JPEG (~15 KB). Dicatat di audit log.

```bash
curl -X PUT $BASE/pegawai/2/wajah -H "Authorization: Bearer $TOKEN" -F "foto=@wajah.jpg"
```

**Response 201 / 200**

```json
{
  "data": {
    "id_wajah": 7, "id_pegawai": 2, "foto_path": "wajah/2026/10/ab12cd.jpg",
    "foto_url": "/api/pegawai/2/wajah/foto?v=7", "created_at": "2026-10-29T10:00:00+08:00"
  }
}
```

**Error:** `FILE_KOSONG`, `FOTO_TIDAK_VALID`, `WAJAH_TIDAK_TERDETEKSI`, `WAJAH_LEBIH_DARI_SATU` (400),
`PEGAWAI_TIDAK_DITEMUKAN` (404).

---

### DELETE `/pegawai/{id_pegawai}/wajah` — Hapus wajah pegawai

Role: ADMIN. Dicatat di audit log.

```bash
curl -X DELETE $BASE/pegawai/2/wajah -H "Authorization: Bearer $TOKEN"
```

**Response 200** — `{ "data": { "message": "Foto wajah dihapus" } }`.
**Error:** `PEGAWAI_TIDAK_DITEMUKAN`, `WAJAH_TIDAK_DITEMUKAN` (404).

---

### GET `/pegawai/{id_pegawai}/wajah/foto` — File foto wajah

Role: ADMIN, OPERATOR, KADES. Response berupa file `image/jpeg`. Pakai `foto_wajah_url` dari data
pegawai (berisi `?v=` yang berubah tiap foto diganti, jadi cache browser otomatis ter-refresh).
Butuh header Authorization, jadi di frontend ambil sebagai blob (`<img src>` tidak bisa kirim token).

```bash
curl "$BASE/pegawai/2/wajah/foto" -H "Authorization: Bearer $TOKEN" -o wajah.jpg
```

**Error:** `WAJAH_TIDAK_DITEMUKAN` (404).

---

## Penduduk

**Objek penduduk**

| Field | Tipe | Wajib (input) | Keterangan |
|---|---|---|---|
| `id_penduduk` | integer | — | Hanya di response |
| `nik` | string | ya | 16 digit angka, unik |
| `nama` | string | ya | |
| `no_kk` | string | tidak | 16 digit angka bila diisi |
| `tempat_lahir` | string | tidak | |
| `tgl_lahir` | date | tidak | `YYYY-MM-DD` |
| `jenis_kelamin` | string | tidak | `L` / `P` |
| `agama` | string | tidak | |
| `status_kawin` | string | tidak | |
| `pekerjaan` | string | tidak | |
| `kewarganegaraan` | string | tidak | Default `Indonesia` |
| `alamat` | string | tidak | |
| `dusun` | string | tidak | |
| `rt` | string | tidak | |
| `rw` | string | tidak | |

### GET `/penduduk` — Daftar penduduk (paginasi)

Role: ADMIN, OPERATOR, KADES. Urut nama.

| Query | Default | Keterangan |
|---|---|---|
| `q` | — | Cari NIK (awalan) atau nama (sebagian, tidak peka huruf besar/kecil) |
| `dusun` | — | Filter dusun (sama persis) |
| `page` | 1 | Halaman |
| `per_page` | 20 | Maks 100 |

```bash
curl "$BASE/penduduk?q=5201&dusun=Bongkot&page=1&per_page=20" -H "Authorization: Bearer $TOKEN"
```

**Response 200**

```json
{
  "data": {
    "items": [
      {
        "id_penduduk": 10,
        "nik": "5201010101900001",
        "no_kk": "5201010101900000",
        "nama": "Ahmad",
        "tempat_lahir": "Lombok Barat",
        "tgl_lahir": "1990-01-01",
        "jenis_kelamin": "L",
        "agama": "Islam",
        "status_kawin": "Kawin",
        "pekerjaan": "Petani",
        "kewarganegaraan": "Indonesia",
        "alamat": "Jl. Contoh No. 1",
        "dusun": "Bongkot",
        "rt": "001",
        "rw": "002"
      }
    ],
    "total": 1,
    "page": 1,
    "per_page": 20
  }
}
```

---

### POST `/penduduk` — Tambah penduduk

Role: ADMIN, OPERATOR.

```bash
curl -X POST $BASE/penduduk \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"nik": "5201010101900001", "nama": "Ahmad", "jenis_kelamin": "L", "tgl_lahir": "1990-01-01", "dusun": "Bongkot"}'
```

**Response 201** — objek penduduk dalam `data`.

**Error:** `FIELD_WAJIB_KOSONG`, `NIK_TIDAK_VALID`, `JENIS_KELAMIN_TIDAK_VALID` (400);
`NIK_SUDAH_TERDAFTAR` (409) dengan `details.id_penduduk` berisi id data yang sudah ada:

```json
{
  "error": {
    "code": "NIK_SUDAH_TERDAFTAR",
    "message": "NIK sudah terdaftar atas nama Ahmad",
    "details": { "id_penduduk": 10 }
  }
}
```

---

### GET `/penduduk/{id_penduduk}` — Detail penduduk

Role: ADMIN, OPERATOR, KADES.

```bash
curl $BASE/penduduk/10 -H "Authorization: Bearer $TOKEN"
```

**Response 200** — objek penduduk dalam `data`. **Error:** `PENDUDUK_TIDAK_DITEMUKAN` (404).

---

### PUT `/penduduk/{id_penduduk}` — Ubah penduduk

Role: ADMIN, OPERATOR. Body sama seperti POST; semua field dikirim ulang. Dicatat di audit log.

```bash
curl -X PUT $BASE/penduduk/10 \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"nik": "5201010101900001", "nama": "Ahmad Fauzi", "jenis_kelamin": "L", "tgl_lahir": "1990-01-01", "dusun": "Bongkot"}'
```

**Response 200** — objek penduduk terbaru.
**Error:** sama seperti POST, ditambah `PENDUDUK_TIDAK_DITEMUKAN` (404).

---

### DELETE `/penduduk/{id_penduduk}` — Hapus penduduk

Role: ADMIN. Dicatat di audit log.

```bash
curl -X DELETE $BASE/penduduk/10 -H "Authorization: Bearer $TOKEN"
```

**Response 200**

```json
{ "data": { "message": "Data penduduk dihapus" } }
```

**Error:** `PENDUDUK_TIDAK_DITEMUKAN` (404).

---

## Persuratan

Alur surat: **DRAFT** → (preview) → **FINAL** (nomor terbit + PDF) atau **BATAL**.
Yang tersedia saat ini: referensi (jenis surat, penandatangan), buat/ubah draft, detail, dan register.

### GET `/persuratan/jenis-surat` — Daftar jenis surat

Role: ADMIN, OPERATOR, KADES.

```bash
curl $BASE/persuratan/jenis-surat -H "Authorization: Bearer $TOKEN"
```

**Response 200**

```json
{
  "data": [
    {
      "id_jenis_surat": 1,
      "kode": "SK_BELUM_MENIKAH",
      "nama": "Surat Keterangan Belum Menikah",
      "judul_surat": "SURAT KETERANGAN BELUM MENIKAH",
      "kode_klasifikasi": "148.1",
      "pakai_subjek": true,
      "field_schema": [
        { "name": "tujuan", "label": "Tujuan", "type": "text", "required": true },
        { "name": "jenis", "label": "Jenis", "type": "select", "options": ["A", "B"] },
        { "name": "isi_tambahan", "label": "Isi tambahan", "type": "richtext" }
      ]
    }
  ]
}
```

- `pakai_subjek`: `true` berarti surat butuh data diri (subjek); `false` berarti tanpa subjek.
- `field_schema`: daftar field tambahan yang harus diisi di `isian` saat membuat draft.
  Frontend bisa membangun form dinamis dari sini. Tipe `select` hanya menerima nilai dari `options`;
  tipe `richtext` boleh berisi HTML sederhana (`p, br, b, strong, i, em, u, ol, ul, li, table, tr, td, th`),
  tag lain dibuang otomatis.

---

### GET `/persuratan/penandatangan` — Daftar penandatangan

Role: ADMIN, OPERATOR, KADES. Penandatangan default tampil paling atas.

```bash
curl $BASE/persuratan/penandatangan -H "Authorization: Bearer $TOKEN"
```

**Response 200**

```json
{
  "data": [
    {
      "id_penandatangan": 1,
      "id_pegawai": 1,
      "nama": "Kepala Desa",
      "jabatan_label": "Kepala Desa",
      "mode": "LANGSUNG",
      "is_default": true
    },
    {
      "id_penandatangan": 2,
      "id_pegawai": 2,
      "nama": "Kaharudin",
      "jabatan_label": "Sekretaris Desa",
      "mode": "AN",
      "is_default": false
    }
  ]
}
```

`mode`: `LANGSUNG` (ditandatangani langsung) atau `AN` (atas nama kepala desa).

---

### GET `/persuratan/surat` — Register surat (paginasi)

Role: ADMIN, OPERATOR, KADES. Urut terbaru dulu.

| Query | Default | Keterangan |
|---|---|---|
| `id_jenis_surat` | — | Filter jenis surat |
| `status_surat` | — | `DRAFT` / `FINAL` / `BATAL` |
| `tahun` | — | Tahun surat (tanggal surat, atau tanggal dibuat untuk draft) |
| `q` | — | Cari nomor surat, NIK (awalan), atau nama subjek |
| `page` | 1 | |
| `per_page` | 20 | Maks 100 |

```bash
curl "$BASE/persuratan/surat?status_surat=DRAFT&tahun=2026&page=1" -H "Authorization: Bearer $TOKEN"
```

**Response 200**

```json
{
  "data": {
    "items": [
      {
        "id_surat": 5,
        "nama_jenis": "Surat Keterangan Belum Menikah",
        "status_surat": "DRAFT",
        "nomor_surat": null,
        "tanggal_surat": null,
        "nik": "5201010101900001",
        "nama": "Ahmad",
        "keperluan": "pengajuan pinjaman di Bank",
        "created_at": "2026-10-27T09:15:00+08:00"
      }
    ],
    "total": 1,
    "page": 1,
    "per_page": 20
  }
}
```

---

### POST `/persuratan/surat` — Buat draft surat

Role: ADMIN, OPERATOR.

**Body**

| Field | Tipe | Wajib | Keterangan |
|---|---|---|---|
| `id_jenis_surat` | integer | ya | |
| `id_penduduk` | integer | salah satu* | **Opsi A**: penduduk yang sudah terdaftar |
| `subjek` | object | salah satu* | **Opsi B**: penduduk belum terdaftar (lihat tabel di bawah) |
| `abaikan_nik_terdaftar` | boolean | tidak | Default `false`. Lihat penjelasan Opsi B |
| `keperluan` | string | tidak | mis. `pengajuan pinjaman di Bank` |
| `isian` | object | sesuai jenis | Field tambahan sesuai `field_schema` jenis surat |
| `id_penandatangan` | integer | tidak | |

\* Hanya untuk jenis surat dengan `pakai_subjek: true`. Bila `id_penduduk` diisi, `subjek` diabaikan.

**Objek `subjek` (Opsi B)**

| Field | Wajib |
|---|---|
| `nik` (16 digit) | ya |
| `nama` | ya |
| `tempat_lahir` | ya |
| `tgl_lahir` (`YYYY-MM-DD`) | ya |
| `jenis_kelamin` (`L`/`P`) | ya |
| `alamat_lengkap` | ya |
| `agama`, `status_kawin`, `pekerjaan` | tidak |
| `kewarganegaraan` | tidak (default `Indonesia`) |

**Cara kerja subjek:**

- **Opsi A** (`id_penduduk`): data diri disalin (snapshot) dari tabel penduduk. `alamat_lengkap`
  disusun otomatis dari alamat, dusun, RT/RW, serta nama desa/kecamatan/kabupaten di pengaturan `desa`.
- **Opsi B** (`subjek`): data diri diisi manual. Bila NIK ternyata **sudah terdaftar**, API menolak
  dengan 409 `NIK_SUDAH_TERDAFTAR` + `details.id_penduduk`. Frontend sebaiknya menawarkan
  "pakai data terdaftar" (kirim ulang dengan Opsi A) atau "tetap pakai data manual"
  (kirim ulang dengan `abaikan_nik_terdaftar: true`).

Setelah tersimpan, kedua opsi sama-sama tersimpan sebagai `data.subjek`, jadi perubahan data
penduduk di kemudian hari tidak mengubah surat.

**Contoh Opsi A**

```bash
curl -X POST $BASE/persuratan/surat \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "id_jenis_surat": 1,
    "id_penduduk": 10,
    "keperluan": "pengajuan pinjaman di Bank",
    "isian": {"tujuan": "Bank BRI"},
    "id_penandatangan": 1
  }'
```

**Contoh Opsi B**

```bash
curl -X POST $BASE/persuratan/surat \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "id_jenis_surat": 1,
    "subjek": {
      "nik": "5201010101900099",
      "nama": "Siti Aminah",
      "tempat_lahir": "Mataram",
      "tgl_lahir": "1995-03-12",
      "jenis_kelamin": "P",
      "alamat_lengkap": "Dusun Bongkot RT 001 RW 002 Desa Karang Bongkot"
    },
    "keperluan": "melamar pekerjaan",
    "isian": {"tujuan": "PT Contoh"}
  }'
```

**Response 201** — objek surat detail (lihat `GET /persuratan/surat/{id_surat}`).

**Error:** `FIELD_WAJIB_KOSONG`, `SUBJEK_TIDAK_LENGKAP`, `NIK_TIDAK_VALID`, `ISIAN_TIDAK_LENGKAP`,
`ISIAN_TIDAK_VALID` (400); `JENIS_SURAT_TIDAK_DITEMUKAN`, `PENDUDUK_TIDAK_DITEMUKAN`,
`PENANDATANGAN_TIDAK_DITEMUKAN` (404); `NIK_SUDAH_TERDAFTAR` (409).

---

### GET `/persuratan/surat/{id_surat}` — Detail surat

Role: ADMIN, OPERATOR, KADES.

```bash
curl $BASE/persuratan/surat/5 -H "Authorization: Bearer $TOKEN"
```

**Response 200**

```json
{
  "data": {
    "id_surat": 5,
    "id_jenis_surat": 1,
    "nama_jenis": "Surat Keterangan Belum Menikah",
    "kode_jenis": "SK_BELUM_MENIKAH",
    "status_surat": "DRAFT",
    "id_penduduk": 10,
    "data": {
      "subjek": {
        "nik": "5201010101900001",
        "nama": "Ahmad",
        "tempat_lahir": "Lombok Barat",
        "tgl_lahir": "1990-01-01",
        "jenis_kelamin": "L",
        "agama": "Islam",
        "status_kawin": "Belum Kawin",
        "pekerjaan": "Petani",
        "kewarganegaraan": "Indonesia",
        "alamat_lengkap": "Jl. Contoh No. 1 Dusun Bongkot RT 001 RW 002 Desa Karang Bongkot Kecamatan Labuapi Kabupaten Lombok Barat"
      },
      "keperluan": "pengajuan pinjaman di Bank",
      "isian": { "tujuan": "Bank BRI" }
    },
    "id_penandatangan": 1,
    "penandatangan": null,
    "nomor_urut": null,
    "nomor_surat": null,
    "tanggal_surat": null,
    "file_pdf": null,
    "alasan_batal": null,
    "created_by": 1,
    "created_at": "2026-10-27T09:15:00+08:00",
    "updated_at": null,
    "finalized_by": null,
    "finalized_at": null,
    "dibatalkan_by": null,
    "dibatalkan_at": null
  }
}
```

Field `penandatangan`, `nomor_*`, `tanggal_surat`, `file_pdf`, dan `finalized_*` baru terisi
setelah finalisasi; `alasan_batal` dan `dibatalkan_*` setelah dibatalkan.

**Error:** `SURAT_TIDAK_DITEMUKAN` (404).

---

### PUT `/persuratan/surat/{id_surat}` — Ubah draft surat

Role: ADMIN, OPERATOR. Hanya untuk surat berstatus `DRAFT`. Body sama seperti POST;
`id_jenis_surat` **tidak bisa diganti** (nilai di body diabaikan, dipakai jenis surat asal).

```bash
curl -X PUT $BASE/persuratan/surat/5 \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"id_jenis_surat": 1, "id_penduduk": 10, "keperluan": "pengajuan KPR", "isian": {"tujuan": "Bank BTN"}, "id_penandatangan": 2}'
```

**Response 200** — objek surat detail terbaru.

**Error:** sama seperti POST, ditambah `SURAT_TIDAK_DITEMUKAN` (404) dan `SURAT_SUDAH_FINAL` (409)
bila status bukan `DRAFT`.

---

## Lokasi Absen

Pengelolaan lokasi absen (titik pusat + radius geofence). Dipakai modul absensi untuk cek radius saat check-in.

**Objek lokasi**

| Field | Tipe | Wajib (input) | Keterangan |
|---|---|---|---|
| `id_lokasi` | integer | — | Hanya di response |
| `nama` | string | ya | mis. `Kantor Desa` |
| `latitude` | number | ya | -90 s/d 90 |
| `longitude` | number | ya | -180 s/d 180 |
| `radius_meter` | integer | tidak | 10 s/d 1000, default 100 |
| `created_at` | datetime | — | Hanya di response |
| `updated_at` | datetime \| null | — | Hanya di response |

`nama` harus unik di antara lokasi aktif (tidak membedakan huruf besar/kecil).

### GET `/lokasi-absen` — Daftar lokasi absen

Role: ADMIN, OPERATOR, KADES. Urut nama.

| Query | Keterangan |
|---|---|
| `q` | Cari nama lokasi (sebagian) |

```bash
curl "$BASE/lokasi-absen?q=kantor" -H "Authorization: Bearer $TOKEN"
```

**Response 200**

```json
{
  "data": [
    { "id_lokasi": 1, "nama": "Kantor Desa", "latitude": -8.62, "longitude": 116.1, "radius_meter": 100,
      "created_at": "2026-10-20T10:00:00+08:00", "updated_at": null }
  ]
}
```

---

### GET `/lokasi-absen/{id_lokasi}` — Detail lokasi absen

Role: ADMIN, OPERATOR, KADES.

```bash
curl $BASE/lokasi-absen/1 -H "Authorization: Bearer $TOKEN"
```

**Response 200** — objek lokasi dalam `data`. **Error:** `LOKASI_TIDAK_DITEMUKAN` (404).

---

### POST `/lokasi-absen` — Tambah lokasi absen

Role: ADMIN.

```bash
curl -X POST $BASE/lokasi-absen \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"nama": "Kantor Desa", "latitude": -8.62, "longitude": 116.1, "radius_meter": 100}'
```

**Response 201** — objek lokasi dalam `data`.

**Error:** `FIELD_WAJIB_KOSONG`, `KOORDINAT_TIDAK_VALID`, `RADIUS_TIDAK_VALID` (400), `LOKASI_SUDAH_ADA` (409).

---

### PUT `/lokasi-absen/{id_lokasi}` — Ubah lokasi absen

Role: ADMIN. Body sama seperti POST; semua field dikirim ulang. Dicatat di audit log.

```bash
curl -X PUT $BASE/lokasi-absen/1 \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"nama": "Kantor Desa", "latitude": -8.6201, "longitude": 116.1003, "radius_meter": 150}'
```

**Response 200** — objek lokasi terbaru.
**Error:** sama seperti POST, ditambah `LOKASI_TIDAK_DITEMUKAN` (404).

---

### DELETE `/lokasi-absen/{id_lokasi}` — Hapus lokasi absen

Role: ADMIN. Dicatat di audit log.

```bash
curl -X DELETE $BASE/lokasi-absen/1 -H "Authorization: Bearer $TOKEN"
```

**Response 200**

```json
{ "data": { "message": "Lokasi absen dihapus" } }
```

**Error:** `LOKASI_TIDAK_DITEMUKAN` (404).

---

## Absensi

Waktu absen **selalu** diambil dari server (WITA), bukan dari HP. Satu baris absensi = satu pegawai satu hari.
Hari kerja tanpa data = **ALPHA** (dihitung saat monitor/rekap). Jadwal & batas diambil dari pengaturan:

| Key pengaturan | Isi (default) |
|---|---|
| `jadwal_kerja` | `{"hari_kerja": [1,2,3,4,5], "jam_masuk": "08:00", "jam_pulang": "14:00", "toleransi_menit": 15}` (1 = Senin ... 7 = Minggu) |
| `absensi` | `{"max_akurasi_meter": 50, "face_threshold": 0.5}` |

**Menit telat** dihitung dari `jam_masuk` jadwal, hanya jika lewat toleransi (08:20 -> telat 20; 08:10 -> 0).
**Menit pulang cepat** = selisih jika pulang sebelum `jam_pulang` jadwal.

### Hak akses

| Siapa | Bisa |
|---|---|
| Akun yang tertaut pegawai (role apa pun) | absen masuk/pulang, status hari ini, riwayat & rekap sendiri, detail & foto absensi sendiri, lihat hari libur |
| ADMIN, OPERATOR, KADES | semua yang bersifat baca: daftar, monitor harian, rekap, detail, foto, log percobaan gagal |
| ADMIN | input manual, koreksi, hapus absensi, kelola hari libur |

### Objek absensi

| Field | Keterangan |
|---|---|
| `id_absensi`, `id_pegawai`, `nama_pegawai`, `jabatan`, `tanggal` | |
| `status_kehadiran` | `HADIR` / `IZIN` / `SAKIT` / `CUTI` / `DINAS` |
| `jadwal_masuk`, `jadwal_pulang`, `toleransi_menit` | snapshot jadwal hari itu |
| `jam_masuk`, `lat_masuk`, `lng_masuk`, `akurasi_masuk`, `id_lokasi_masuk`, `nama_lokasi_masuk`, `skor_masuk`, `foto_masuk_url` | data absen masuk (`null` kalau belum / input manual) |
| `jam_pulang`, ... `foto_pulang_url` | sama untuk pulang |
| `menit_telat`, `menit_pulang_cepat` | integer |
| `keterangan` | alasan input manual / koreksi |
| `is_koreksi` | `true` kalau diinput manual atau dikoreksi admin |
| `created_at`, `updated_at`, ... | |

---

### POST `/absensi/masuk` — Absen masuk &nbsp;·&nbsp; POST `/absensi/pulang` — Absen pulang

`multipart/form-data`:

| Field | Tipe | Keterangan |
|---|---|---|
| `foto` | file | selfie dari kamera, satu wajah |
| `latitude`, `longitude` | number | dari GPS HP |
| `akurasi` | number | meter (`position.coords.accuracy`) |

Urutan validasi: wajah terdaftar -> hari kerja -> belum absen -> akurasi GPS -> radius lokasi terdekat -> wajah cocok.
Percobaan yang gagal (hari libur, akurasi, radius, wajah) **dicatat** ke log percobaan untuk admin.

```bash
curl -X POST $BASE/absensi/masuk -H "Authorization: Bearer $TOKEN" \
  -F "foto=@selfie.jpg" -F "latitude=-8.6201" -F "longitude=116.1001" -F "akurasi=12"
```

**Response** — masuk **201**, pulang **200**, objek absensi dalam `data`.

| Error | Status | Arti / tampilan di HP |
|---|---|---|
| `FIELD_WAJIB_KOSONG`, `PARAMETER_TIDAK_VALID`, `FILE_KOSONG` | 400 | input tidak lengkap |
| `WAJAH_BELUM_TERDAFTAR` | 400 | hubungi admin untuk daftar wajah |
| `LOKASI_BELUM_DIATUR` | 400 | admin belum membuat lokasi absen |
| `BUKAN_HARI_KERJA` | 400 | hari libur / akhir pekan |
| `AKURASI_GPS_RENDAH` | 400 | `details`: `akurasi`, `max_akurasi_meter` |
| `DI_LUAR_RADIUS` | 400 | `details`: `jarak_meter`, `nama_lokasi`, `radius_meter` |
| `FOTO_TIDAK_VALID`, `WAJAH_TIDAK_TERDETEKSI`, `WAJAH_LEBIH_DARI_SATU` | 400 | ulangi foto |
| `WAJAH_TIDAK_COCOK` | 400 | `details`: `skor_wajah`, `threshold` |
| `BELUM_ABSEN_MASUK` | 400 | (pulang) belum absen masuk |
| `BUKAN_PEGAWAI` | 403 | akun tidak tertaut pegawai |
| `SUDAH_ABSEN_MASUK`, `SUDAH_ABSEN_PULANG` | 409 | sudah absen |
| `SUDAH_ADA_KETERANGAN` | 409 | hari ini tercatat IZIN/SAKIT/CUTI/DINAS |

---

### GET `/absensi/saya/hari-ini` — Status absen saya hari ini

Untuk layar absen: tentukan tombol mana yang aktif.

```json
{
  "data": {
    "tanggal": "2026-10-29", "hari_kerja": true, "libur": null,
    "jadwal": { "jam_masuk": "08:00:00", "jam_pulang": "14:00:00", "toleransi_menit": 15 },
    "wajah_terdaftar": true,
    "absensi": { "...objek absensi atau null..." },
    "bisa_masuk": false, "bisa_pulang": true
  }
}
```

### GET `/absensi/saya?bulan=&tahun=` — Riwayat & rekap saya

Default bulan berjalan. `data`: `{bulan, tahun, rekap: <objek rekap>, items: [<objek absensi>]}`.

---

### GET `/absensi/harian?tanggal=` — Monitor harian (ADMIN, OPERATOR, KADES)

Semua pegawai aktif + status pada tanggal itu (default hari ini).
`status`: `HADIR`/`IZIN`/`SAKIT`/`CUTI`/`DINAS`/`BELUM_ABSEN` (hari ini, belum absen)/`ALPHA` (hari sudah lewat)/`LIBUR`.

```json
{
  "data": {
    "tanggal": "2026-10-29", "hari_kerja": true, "libur": null,
    "ringkasan": { "HADIR": 5, "BELUM_ABSEN": 2 },
    "items": [
      { "id_pegawai": 2, "nama": "Kaharudin", "jabatan": "Sekretaris Desa",
        "foto_wajah_url": "/api/pegawai/2/wajah/foto?v=7", "status": "HADIR", "absensi": { "..." } }
    ]
  }
}
```

### GET `/absensi` — Daftar absensi (ADMIN, OPERATOR, KADES)

Query: `tanggal_mulai`, `tanggal_selesai` (YYYY-MM-DD), `id_pegawai`, `status`, `page`, `per_page` (maks 100).
`data`: `{items, total, page, per_page}`.

### GET `/absensi/rekap?bulan=&tahun=&id_pegawai=` — Rekap bulanan (ADMIN, OPERATOR, KADES)

`data`: `{bulan, tahun, items: [<objek rekap>]}`. **Objek rekap**:

| Field | Keterangan |
|---|---|
| `id_pegawai`, `nama`, `jabatan` | |
| `hari_kerja` | hari kerja sebulan (tanpa libur, sejak `tanggal_mulai` pegawai) |
| `hadir`, `izin`, `sakit`, `cuti`, `dinas` | jumlah hari |
| `telat_kali`, `telat_menit`, `pulang_cepat_kali`, `pulang_cepat_menit` | |
| `tidak_absen_pulang` | hadir tapi tidak absen pulang (hari yang sudah lewat) |
| `alpha` | hari kerja yang sudah lewat tanpa data (hari ini belum dihitung) |

### GET `/absensi/{id_absensi}` — Detail

ADMIN/OPERATOR/KADES: semua; role lain: hanya miliknya (selain itu 404 `ABSENSI_TIDAK_DITEMUKAN`).

### GET `/absensi/{id_absensi}/foto/{masuk|pulang}` — Foto absen

File `image/jpeg`, aturan akses sama dengan detail. Pakai `foto_masuk_url` / `foto_pulang_url`.

---

### POST `/absensi` — Input manual (ADMIN)

Untuk pegawai yang tidak bisa absen lewat HP, atau mencatat IZIN/SAKIT/CUTI/DINAS.

| Field | Wajib | Keterangan |
|---|---|---|
| `id_pegawai` | ya | |
| `tanggal` | ya | YYYY-MM-DD |
| `status_kehadiran` | tidak | default `HADIR` |
| `jam_masuk` | jika HADIR | `HH:MM` |
| `jam_pulang` | tidak | `HH:MM`, harus setelah `jam_masuk` |
| `keterangan` | ya | alasan |

```bash
curl -X POST $BASE/absensi -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"id_pegawai": 2, "tanggal": "2026-10-28", "jam_masuk": "08:05", "jam_pulang": "14:00", "keterangan": "HP rusak"}'
curl -X POST $BASE/absensi -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"id_pegawai": 2, "tanggal": "2026-10-27", "status_kehadiran": "SAKIT", "keterangan": "Demam, ada surat dokter"}'
```

**Response 201.** **Error:** `FIELD_WAJIB_KOSONG`, `PARAMETER_TIDAK_VALID`, `TANGGAL_TIDAK_VALID` (HADIR di tanggal yang akan datang) (400),
`PEGAWAI_TIDAK_DITEMUKAN` (404), `ABSENSI_SUDAH_ADA` (409, `details.id_absensi` -> pakai koreksi).

### PUT `/absensi/{id_absensi}` — Koreksi (ADMIN)

Body: `status_kehadiran`, `jam_masuk`, `jam_pulang`, `keterangan` (wajib, alasan koreksi). Semua dikirim ulang
(isi form dari data lama). Menit telat dihitung ulang dari jadwal hari itu. Dicatat di audit log.

### DELETE `/absensi/{id_absensi}` — Hapus (ADMIN)

Data lama tersimpan di audit log.

---

### GET `/absensi/percobaan` — Log percobaan absen gagal (ADMIN, OPERATOR, KADES)

Query: `tanggal_mulai`, `tanggal_selesai`, `id_pegawai`, `page`, `per_page`. Item: `id_percobaan`, `id_pegawai`, `nama_pegawai`,
`tipe`, `alasan_gagal`, `latitude`, `longitude`, `akurasi`, `jarak_meter`, `skor_wajah`, `foto_url` (hanya untuk `WAJAH_TIDAK_COCOK`), `created_at`.
Foto: GET `/absensi/percobaan/{id_percobaan}/foto`.

---

### Hari libur

| Method | Path | Role | Body |
|---|---|---|---|
| GET | `/absensi/hari-libur?tahun=` | semua | - |
| POST | `/absensi/hari-libur` | ADMIN | `{"tanggal": "2026-12-25", "keterangan": "Hari Raya Natal"}` |
| PUT | `/absensi/hari-libur/{tanggal}` | ADMIN | `{"keterangan": "..."}` |
| DELETE | `/absensi/hari-libur/{tanggal}` | ADMIN | - |

**Error:** `HARI_LIBUR_SUDAH_ADA` (409), `HARI_LIBUR_TIDAK_DITEMUKAN` (404).

---

## Ringkasan semua endpoint

Semua path diawali `/api`.

| Method | Path | Role | Fungsi |
|---|---|---|---|
| POST | `/auth/login` | — (tanpa token) | Login |
| POST | `/auth/login-absensi` | publik | Login aplikasi absensi (hanya akun pegawai) |
| GET | `/auth/me` | Semua login | Data akun sendiri |
| POST | `/auth/ganti-password` | Semua login | Ganti password sendiri |
| GET | `/admin/users` | ADMIN | Daftar user |
| POST | `/admin/users` | ADMIN | Buat user |
| GET | `/admin/users/{id_user}` | ADMIN | Detail user |
| PUT | `/admin/users/{id_user}` | ADMIN | Ubah user |
| PUT | `/admin/users/{id_user}/reset-password` | ADMIN | Reset password user |
| DELETE | `/admin/users/{id_user}` | ADMIN | Hapus user |
| GET | `/pengaturan` | ADMIN, OPERATOR, KADES | Semua pengaturan |
| GET | `/pengaturan/{key}` | Semua login | Satu pengaturan |
| PUT | `/pengaturan/{key}` | ADMIN | Simpan pengaturan |
| GET | `/pegawai` | ADMIN, OPERATOR, KADES | Daftar pegawai |
| POST | `/pegawai` | ADMIN | Tambah pegawai |
| GET | `/pegawai/{id_pegawai}` | ADMIN, OPERATOR, KADES | Detail pegawai |
| PUT | `/pegawai/{id_pegawai}` | ADMIN | Ubah pegawai |
| DELETE | `/pegawai/{id_pegawai}` | ADMIN | Hapus pegawai |
| PUT | `/pegawai/{id_pegawai}/wajah` | ADMIN | Simpan wajah (tambah / ganti, multipart) |
| DELETE | `/pegawai/{id_pegawai}/wajah` | ADMIN | Hapus wajah |
| GET | `/pegawai/{id_pegawai}/wajah/foto` | ADMIN, OPERATOR, KADES | File foto wajah (JPEG) |
| GET | `/penduduk` | ADMIN, OPERATOR, KADES | Daftar penduduk (paginasi) |
| POST | `/penduduk` | ADMIN, OPERATOR | Tambah penduduk |
| GET | `/penduduk/{id_penduduk}` | ADMIN, OPERATOR, KADES | Detail penduduk |
| PUT | `/penduduk/{id_penduduk}` | ADMIN, OPERATOR | Ubah penduduk |
| DELETE | `/penduduk/{id_penduduk}` | ADMIN | Hapus penduduk |
| GET | `/persuratan/jenis-surat` | ADMIN, OPERATOR, KADES | Daftar jenis surat |
| GET | `/persuratan/penandatangan` | ADMIN, OPERATOR, KADES | Daftar penandatangan |
| GET | `/persuratan/surat` | ADMIN, OPERATOR, KADES | Register surat (paginasi) |
| POST | `/persuratan/surat` | ADMIN, OPERATOR | Buat draft surat |
| GET | `/persuratan/surat/{id_surat}` | ADMIN, OPERATOR, KADES | Detail surat |
| PUT | `/persuratan/surat/{id_surat}` | ADMIN, OPERATOR | Ubah draft surat |
| GET | `/lokasi-absen` | ADMIN, OPERATOR, KADES | Daftar lokasi absen |
| GET | `/lokasi-absen/{id_lokasi}` | ADMIN, OPERATOR, KADES | Detail lokasi absen |
| POST | `/lokasi-absen` | ADMIN | Tambah lokasi absen |
| PUT | `/lokasi-absen/{id_lokasi}` | ADMIN | Ubah lokasi absen |
| DELETE | `/lokasi-absen/{id_lokasi}` | ADMIN | Hapus lokasi absen |
| POST | `/absensi/masuk` | pegawai | Absen masuk (multipart) |
| POST | `/absensi/pulang` | pegawai | Absen pulang (multipart) |
| GET | `/absensi/saya/hari-ini` | pegawai | Status absen hari ini |
| GET | `/absensi/saya` | pegawai | Riwayat & rekap bulanan sendiri |
| GET | `/absensi` | ADMIN, OPERATOR, KADES | Daftar absensi (filter, paginasi) |
| POST | `/absensi` | ADMIN | Input absensi manual |
| GET | `/absensi/harian` | ADMIN, OPERATOR, KADES | Monitor harian |
| GET | `/absensi/rekap` | ADMIN, OPERATOR, KADES | Rekap bulanan |
| GET | `/absensi/{id_absensi}` | monitor / pemilik | Detail absensi |
| PUT | `/absensi/{id_absensi}` | ADMIN | Koreksi absensi |
| DELETE | `/absensi/{id_absensi}` | ADMIN | Hapus absensi |
| GET | `/absensi/{id_absensi}/foto/{masuk\|pulang}` | monitor / pemilik | Foto absen |
| GET | `/absensi/percobaan` | ADMIN, OPERATOR, KADES | Log percobaan gagal |
| GET | `/absensi/percobaan/{id}/foto` | ADMIN, OPERATOR, KADES | Foto percobaan gagal |
| GET | `/absensi/hari-libur` | semua | Daftar hari libur |
| POST | `/absensi/hari-libur` | ADMIN | Tambah hari libur |
| PUT / DELETE | `/absensi/hari-libur/{tanggal}` | ADMIN | Ubah / hapus hari libur |

---

## Endpoint yang direncanakan

Belum tersedia; dicatat agar frontend bisa bersiap.

**Persuratan**

| Method | Path | Fungsi |
|---|---|---|
| GET | `/persuratan/surat/{id}/preview` | Preview PDF (tanpa nomor, tidak disimpan) |
| POST | `/persuratan/surat/{id}/finalisasi` | Terbitkan nomor surat + simpan PDF |
| GET | `/persuratan/surat/{id}/pdf` | Unduh PDF final |
| POST | `/persuratan/surat/{id}/batal` | Batalkan surat (wajib alasan) |
| GET | `/persuratan/register/export` | Export buku register (xlsx) |

**Absensi**

| Method | Path | Fungsi |
|---|---|---|
| POST / GET / PUT | `/absensi/izin`, `/absensi/izin/{id}/proses` | Pengajuan izin oleh pegawai & proses (setujui/tolak) oleh admin |
