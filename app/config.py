import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL

from app.core.db import json_default

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _env(key, default=None, required=False):
    value = os.getenv(key, default)
    if required and not value:
        raise RuntimeError(f"Environment variable {key} wajib diisi di .env")
    return value


class Config:
    # URL.create meng-escape karakter khusus di password secara otomatis
    DATABASE_URL = URL.create(
        drivername="postgresql+psycopg",
        username=_env("DB_USER", required=True),
        password=_env("DB_PASSWORD", required=True),
        host=_env("DB_HOST", "localhost"),
        port=int(_env("DB_PORT", "5432")),
        database=_env("DB_NAME", required=True),
    )

    # Per proses/worker. Total koneksi maks = workers x (DB_POOL_SIZE + DB_MAX_OVERFLOW)
    DB_POOL_SIZE = int(_env("DB_POOL_SIZE", "2"))
    DB_MAX_OVERFLOW = int(_env("DB_MAX_OVERFLOW", "3"))
    DB_POOL_TIMEOUT = int(_env("DB_POOL_TIMEOUT", "10"))

    JWT_SECRET_KEY =_env("JWT_SECRET_KEY", required=True)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(_env("JWT_EXPIRES_HOURS", "12")))

    STORAGE_DIR = (BASE_DIR / _env("STORAGE_DIR", "./storage")).resolve()
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB per request (foto absensi, lampiran)

    CORS_ORIGINS = [o.strip() for o in _env("CORS_ORIGINS", "").split(",") if o.strip()]

    # Wajib untuk flask-restx + flask-jwt-extended: tanpa ini error JWT berubah jadi 500
    PROPAGATE_EXCEPTIONS = True

    # Serialisasi date/datetime/Decimal di response restx
    RESTX_JSON = {"default": json_default, "ensure_ascii": False}
    RESTX_MASK_SWAGGER = False
    ERROR_404_HELP = False
