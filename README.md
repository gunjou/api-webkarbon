# Backend Sistem Kantor Desa

Flask + flask_restx + PostgreSQL (raw SQL via `sqlalchemy.text`, tanpa ORM/migration).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # lalu isi kredensial

psql -h <host> -U <user> -d <db> -f db/schema.sql   # sekali, saat setup awal
psql -h <host> -U <user> -d <db> -f db/seed.sql
python -m scripts.create_admin

python wsgi.py                  # dev, http://localhost:5000/docs
gunicorn -c gunicorn.conf.py wsgi:app   # produksi (3 worker, maks 15 koneksi DB)
```

WeasyPrint butuh library sistem (Debian/Ubuntu):
`apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b`

## Pola kode per modul

| File | Isi |
|---|---|
| `routes.py` | Namespace restx: parsing input, cek role, panggil service |
| `service.py` | Logika bisnis, **pemilik transaksi** (`with get_connection().begin() as conn`) |
| `queries.py` | SQL murni, setiap fungsi menerima `conn` |

- Error bisnis: `raise AppError(code, message, status)`. Jangan `try/except` error database
  di setiap fungsi; handler global yang mencatat & mengembalikan 500.
- Modul lain dipakai lewat fungsi service-nya (mis. `kependudukan.service.get_penduduk(conn, id)`),
  bukan query langsung ke tabel modul lain.
- Waktu selalu `now_wita()` / `today_wita()`.
- Response sukses: `{"data": ...}`. Response error: `{"error": {"code", "message", "details"}}`.
- Label pemakai di awal judul Swagger (baris pertama docstring), **wajib untuk setiap endpoint**:

  | Label | Dipakai untuk | Biasanya |
  |---|---|---|
  | `(pegawai)` | aplikasi pegawai, data milik sendiri | `@roles_required()` + `current_pegawai_id()` |
  | `(admin)` | panel admin | `@roles_required(ADMIN, ...)` (ADMIN / OPERATOR / KADES) |
  | `(pegawai & admin)` | dipakai keduanya; pegawai hanya melihat datanya sendiri | `@roles_required()` |
  | `(publik)` | tanpa token | mis. login |

  Contoh: `"""(admin) Monitor harian`. Dicek otomatis oleh `tests/test_swagger_labels.py`.
- Dokumentasi Swagger (`/docs`): setiap method diberi docstring (baris pertama = judul, sebutkan role),
  `@ns.response(..., docs.envelope(ns, model))` dan `@docs.errors(ns, 401, 403, ...)` dari `app/core/docs.py`.
  Helper ini hanya dokumentasi, tidak mengubah response.

## Perubahan skema

Jangan edit `db/schema.sql` yang sudah dijalankan di server. Buat file baru di `db/patches/`
dengan nomor urut (`001_xxx.sql`, `002_xxx.sql`), jalankan dengan `psql -f`,
lalu sesuaikan juga `schema.sql` supaya setup baru tetap lengkap.

## Menambah modul (mis. payroll)

1. Buat `app/modules/payroll/` berisi `__init__.py` (fungsi `register(api)`), `routes.py`, `service.py`, `queries.py`.
2. Tambahkan ke daftar `MODULES` di `app/modules/__init__.py`.
3. Tabel baru lewat `db/patches/`.
