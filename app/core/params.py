"""
Parser nilai input (query string / form / JSON) -> tipe Python.
Gagal parse -> AppError 400 PARAMETER_TIDAK_VALID, jadi format error tetap {"error": {...}}
(berbeda dengan reqparse.parse_args() milik flask-restx yang punya format error sendiri).

Pemakaian:
    tgl = params.tanggal(args.get("tanggal"), "tanggal", wajib=True)
    bulan, tahun = params.bulan_tahun(args)
"""
from datetime import date, time

from app.core.db import today_wita
from app.core.errors import AppError


def _salah(field, pesan):
    raise AppError("PARAMETER_TIDAK_VALID", f"{field}: {pesan}", 400, {"field": field})


def _kosong(value):
    return value is None or (isinstance(value, str) and not value.strip())


def _wajib(field):
    raise AppError("FIELD_WAJIB_KOSONG", f"Field wajib belum diisi: {field}", 400, {"fields": [field]})


def tanggal(value, field, wajib=False):
    """'YYYY-MM-DD' -> date."""
    if _kosong(value):
        return _wajib(field) if wajib else None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        _salah(field, "format tanggal harus YYYY-MM-DD")


def jam(value, field, wajib=False):
    """'HH:MM' atau 'HH:MM:SS' -> time."""
    if _kosong(value):
        return _wajib(field) if wajib else None
    try:
        return time.fromisoformat(str(value).strip())
    except ValueError:
        _salah(field, "format jam harus HH:MM")


def angka(value, field, wajib=False, minimal=None, maksimal=None):
    """Angka desimal (float), opsional dengan batas rentang."""
    if _kosong(value):
        return _wajib(field) if wajib else None
    try:
        hasil = float(value)
    except (TypeError, ValueError):
        _salah(field, "harus berupa angka")
    if (minimal is not None and hasil < minimal) or (maksimal is not None and hasil > maksimal):
        _salah(field, f"harus antara {minimal} s/d {maksimal}")
    return hasil


def bilangan(value, field, wajib=False, default=None, minimal=None, maksimal=None):
    """Bilangan bulat (int)."""
    if _kosong(value):
        return _wajib(field) if wajib else default
    try:
        hasil = int(value)
    except (TypeError, ValueError):
        _salah(field, "harus berupa bilangan bulat")
    if (minimal is not None and hasil < minimal) or (maksimal is not None and hasil > maksimal):
        _salah(field, f"harus antara {minimal} s/d {maksimal}")
    return hasil


def pilihan(value, field, opsi, wajib=False, default=None):
    """Nilai harus salah satu dari opsi (case-insensitive, dikembalikan UPPERCASE)."""
    if _kosong(value):
        return _wajib(field) if wajib else default
    v = str(value).strip().upper()
    if v not in opsi:
        _salah(field, f"harus salah satu dari: {', '.join(opsi)}")
    return v


def bulan_tahun(args):
    """?bulan=&tahun= -> (bulan, tahun); default bulan & tahun berjalan (WITA)."""
    hari_ini = today_wita()
    return (bilangan(args.get("bulan"), "bulan", default=hari_ini.month, minimal=1, maksimal=12),
            bilangan(args.get("tahun"), "tahun", default=hari_ini.year, minimal=2000, maksimal=2100))


def rentang_tanggal(args, field_mulai="tanggal_mulai", field_selesai="tanggal_selesai"):
    mulai = tanggal(args.get(field_mulai), field_mulai)
    selesai = tanggal(args.get(field_selesai), field_selesai)
    if mulai and selesai and selesai < mulai:
        _salah(field_selesai, f"tidak boleh sebelum {field_mulai}")
    return mulai, selesai


def halaman(args, default_per_page=20, max_per_page=100):
    """?page=&per_page= -> (page, per_page, offset)."""
    page = bilangan(args.get("page"), "page", default=1, minimal=1)
    per_page = bilangan(args.get("per_page"), "per_page", default=default_per_page, minimal=1,
                        maksimal=max_per_page)
    return page, per_page, (page - 1) * per_page
