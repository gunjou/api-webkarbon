"""
Penyimpanan file (PDF surat, foto absensi, foto wajah, lampiran izin).
Yang disimpan di database hanya path relatif, mis. 'absensi/2026/10/ab12...jpg'.
Kalau nanti pindah ke MinIO/S3, cukup ganti isi file ini.
"""
import uuid
from pathlib import Path

from flask import current_app

from app.core.db import now_wita
from app.core.errors import AppError


def _root():
    return Path(current_app.config["STORAGE_DIR"])


def save_bytes(data: bytes, folder: str, ext: str) -> str:
    now = now_wita()
    rel = Path(folder) / f"{now:%Y}" / f"{now:%m}" / f"{uuid.uuid4().hex}.{ext.lstrip('.')}"
    target = _root() / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return rel.as_posix()


def save_upload(file_storage, folder: str, allowed_ext=("jpg", "jpeg", "png", "pdf")) -> str:
    """Simpan werkzeug FileStorage dari request.files."""
    if not file_storage or not file_storage.filename:
        raise AppError("FILE_KOSONG", "File belum dipilih", 400)
    ext = file_storage.filename.rsplit(".", 1)[-1].lower() if "." in file_storage.filename else ""
    if ext not in allowed_ext:
        raise AppError("FORMAT_FILE_TIDAK_DIDUKUNG", f"Format yang diizinkan: {', '.join(allowed_ext)}", 400)
    return save_bytes(file_storage.read(), folder, ext)


def absolute_path(rel_path: str) -> Path:
    """Path absolut, dengan proteksi path traversal (../)."""
    root = _root().resolve()
    target = (root / rel_path).resolve()
    if root not in target.parents:
        raise AppError("PATH_TIDAK_VALID", "Path file tidak valid", 400)
    if not target.exists():
        raise AppError("FILE_TIDAK_DITEMUKAN", "File tidak ditemukan", 404)
    return target
