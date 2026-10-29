import logging

from flask import Blueprint, Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_restx import Api

from app.config import Config
from app.core.db import init_engine
from app.core.errors import register_error_handlers, register_jwt_handlers
from app.modules import MODULES


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

    init_engine(app.config["DATABASE_URL"], app.config["DB_POOL_SIZE"],
                app.config["DB_MAX_OVERFLOW"], app.config["DB_POOL_TIMEOUT"])

    jwt = JWTManager(app)
    register_jwt_handlers(jwt)

    if app.config["CORS_ORIGINS"]:
        CORS(app, origins=app.config["CORS_ORIGINS"])

    # Prefix /api dipasang di Api (bukan di Blueprint) supaya Swagger UI bisa di /docs,
    # sementara endpoint tetap di /api/... dan spec di /api/swagger.json
    blueprint = Blueprint("api", __name__)
    api = Api(
        blueprint,
        prefix="/api",
        title="API Sistem Kantor Desa",
        version="1.0",
        description=(
            "Semua response sukses berbentuk `{\"data\": ...}`, response error berbentuk "
            "`{\"error\": {\"code\", \"message\", \"details\"}}`.\n\n"
            "Login lewat **POST /api/auth/login**, lalu klik **Authorize** dan isi "
            "`Bearer <access_token>`."
        ),
        doc="/docs",  # Swagger UI: /docs
        authorizations={"Bearer": {"type": "apiKey", "in": "header", "name": "Authorization",
                                   "description": "Isi dengan: Bearer <token>"}},
        security="Bearer",
    )
    register_error_handlers(app, api)

    # Setiap modul mendaftarkan namespace-nya sendiri.
    # Menambah fitur baru (mis. payroll) = tambah folder modul + daftarkan di app/modules/__init__.py
    for module in MODULES:
        module.register(api)

    app.register_blueprint(blueprint)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
