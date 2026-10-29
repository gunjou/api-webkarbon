from functools import wraps

from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request

from app.core.errors import AppError

ADMIN = "ADMIN"
OPERATOR = "OPERATOR"
PEGAWAI = "PEGAWAI"
KADES = "KADES"

# Klaim "app" di JWT: dari frontend mana token dibuat
APP_ADMIN = "ADMIN"        # panel admin   -> POST /auth/login
APP_ABSENSI = "ABSENSI"    # aplikasi absen -> POST /auth/login-absensi (hanya akun yang tertaut pegawai)


def current_app_token():
    """Token lama tanpa klaim "app" dianggap token panel admin."""
    return get_jwt().get("app") or APP_ADMIN


def roles_required(*roles):
    """
    @roles_required()                  -> cukup login (token admin maupun absensi)
    @roles_required(ADMIN, OPERATOR)   -> login + role tertentu + token dari panel admin
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            if roles and get_jwt().get("role") not in roles:
                raise AppError("AKSES_DITOLAK", "Anda tidak memiliki akses ke fitur ini", 403)
            if roles and current_app_token() != APP_ADMIN:
                raise AppError("AKSES_DITOLAK", "Fitur ini hanya untuk panel admin. Login lewat /auth/login", 403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def current_user_id():
    return int(get_jwt_identity())


def optional_user_id():
    """id_user kalau request membawa token, None kalau tanpa token (mis. saat roles_required di-comment)."""
    verify_jwt_in_request(optional=True)
    identity = get_jwt_identity()
    return int(identity) if identity else None


def current_role():
    return get_jwt().get("role")


def current_pegawai_id():
    """id_pegawai dari user yang login; raise kalau user tidak tertaut ke pegawai."""
    id_pegawai = get_jwt().get("id_pegawai")
    if not id_pegawai:
        raise AppError("BUKAN_PEGAWAI", "Akun ini tidak tertaut ke data pegawai", 403)
    return id_pegawai
