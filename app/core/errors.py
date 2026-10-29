"""
Satu format error untuk seluruh API:
    {"error": {"code": "NIK_SUDAH_TERDAFTAR", "message": "...", "details": ...}}

Di service cukup `raise AppError(...)`. Error database TIDAK perlu di-try/except
di setiap fungsi: biarkan naik, handler global yang mencatat ke log dan mengembalikan 500.
"""
import logging

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.exceptions import HTTPException

log = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(self, code, message, status=400, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details


def error_body(code, message, details=None):
    body = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return body


def require_fields(payload, fields):
    """Validasi field wajib sederhana. Raise AppError kalau ada yang kosong."""
    payload = payload or {}
    kurang = [f for f in fields if payload.get(f) in (None, "", [])]
    if kurang:
        raise AppError("FIELD_WAJIB_KOSONG", f"Field wajib belum diisi: {', '.join(kurang)}",
                       400, {"fields": kurang})


def register_error_handlers(app, api):
    @api.errorhandler(AppError)
    def handle_app_error(e):
        return error_body(e.code, e.message, e.details), e.status

    @api.errorhandler(IntegrityError)
    def handle_integrity_error(e):
        log.warning("IntegrityError: %s", e.orig)
        return error_body("DATA_KONFLIK", "Data bertentangan dengan data yang sudah ada"), 409

    @api.errorhandler(SQLAlchemyError)
    def handle_db_error(e):
        log.exception("Database error")
        return error_body("DATABASE_ERROR", "Terjadi kesalahan pada database"), 500

    # Untuk error di luar namespace restx (mis. /health) dan error tak terduga
    @app.errorhandler(Exception)
    def handle_unexpected(e):
        if isinstance(e, HTTPException):
            return error_body(e.name.upper().replace(" ", "_"), e.description), e.code
        log.exception("Unhandled error")
        return error_body("INTERNAL_ERROR", "Terjadi kesalahan pada server"), 500


def register_jwt_handlers(jwt):
    @jwt.unauthorized_loader
    def missing_token(reason):
        return error_body("TOKEN_TIDAK_ADA", "Silakan login terlebih dahulu"), 401

    @jwt.invalid_token_loader
    def invalid_token(reason):
        return error_body("TOKEN_TIDAK_VALID", "Token tidak valid"), 401

    @jwt.expired_token_loader
    def expired_token(header, payload):
        return error_body("TOKEN_KEDALUWARSA", "Sesi berakhir, silakan login kembali"), 401
