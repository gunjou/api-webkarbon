"""
Koneksi database & helper umum.

Pola pemakaian:
    - service.py membuka transaksi:   with get_connection().begin() as conn: ...
    - queries.py menerima conn:      def get_x(conn, id): ...
Semua query dalam satu operasi bisnis memakai conn yang sama (satu transaksi).

Satu engine (= satu pool) per proses. `with` mengembalikan koneksi ke pool, bukan menutupnya,
jadi koneksi dipakai ulang antar request. Total koneksi maksimum ke PostgreSQL:
    jumlah worker gunicorn x (pool_size + max_overflow)
"""
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine

WITA = ZoneInfo("Asia/Makassar")

_engine = None


def init_engine(url, pool_size=2, max_overflow=3, pool_timeout=10):
    """
    Dipanggil di create_app(). Aman dipanggil berulang (tests, script): engine lama
    di-dispose dulu supaya koneksinya tertutup dan tidak tertinggal di server.

    Default kecil karena worker gunicorn sync hanya melayani 1 request sekaligus,
    jadi dalam praktik cukup 1 koneksi per worker; sisanya cadangan.
    """
    global _engine
    dispose_engine()
    _engine = create_engine(
        url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,  # detik menunggu koneksi kosong sebelum error (default 30)
        pool_pre_ping=True,         # buang koneksi mati sebelum dipakai
        pool_recycle=1800,          # ganti koneksi yang umurnya > 30 menit
        connect_args={
            "application_name": "api-webkarbon",  # mudah dipantau di pg_stat_activity
            # timestamptz keluar sebagai +08:00 & ::date dihitung per hari WITA (bukan UTC)
            "options": "-c timezone=Asia/Makassar",
        },
    )
    return _engine


def dispose_engine(close=True):
    """
    Tutup semua koneksi idle di pool. close=False dipakai setelah fork (gunicorn --preload):
    proses anak membuang koneksi warisan tanpa menutup socket milik proses induk.
    """
    if _engine is not None:
        _engine.dispose(close=close)


def get_connection():
    """Mengembalikan engine singleton (bukan membuat engine baru)."""
    if _engine is None:
        raise RuntimeError("Engine belum diinisialisasi. Panggil init_engine() di create_app().")
    return _engine


def now_wita():
    return datetime.now(WITA)


def today_wita():
    return now_wita().date()


def row(result):
    """Ambil satu baris sebagai dict, atau None."""
    r = result.mappings().first()
    return dict(r) if r else None


def rows(result):
    """Ambil semua baris sebagai list of dict."""
    return [dict(r) for r in result.mappings().all()]


def json_default(value):
    """Dipakai json.dumps untuk tipe yang tidak didukung bawaan."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Tipe {type(value).__name__} tidak bisa diserialisasi ke JSON")
