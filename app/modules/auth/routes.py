from flask import request
from flask_restx import Namespace, Resource, fields

from app.core import docs
from app.core.auth import current_user_id, roles_required

from . import service

ns = Namespace("Auth", description="Login dan akun")

login_model = ns.model("Login", {
    "username": fields.String(required=True, example="cobauser"),
    "password": fields.String(required=True, example="aniku"),
})

ganti_password_model = ns.model("GantiPassword", {
    "password_lama": fields.String(required=True),
    "password_baru": fields.String(required=True, description="Minimal 5 karakter"),
})

user_model = ns.model("User", {
    "id_user": fields.Integer(example=1),
    "username": fields.String(example="admin"),
    "nama": fields.String(example="Administrator"),
    "role": fields.String(enum=["ADMIN", "OPERATOR", "PEGAWAI", "KADES"]),
    "id_pegawai": fields.Integer(description="Terisi kalau akun tertaut ke data pegawai"),
})

login_result_model = ns.model("LoginResult", {
    "access_token": fields.String(description="JWT, kirim di header: Authorization: Bearer <token>"),
    "app": fields.String(enum=["ADMIN", "ABSENSI"], description="Klaim 'app' di JWT"),
    "user": fields.Nested(user_model),
})

pegawai_login_model = ns.model("LoginPegawai", {
    "id_pegawai": fields.Integer(example=2),
    "nama": fields.String(example="Kaharudin"),
    "jabatan": fields.String(example="Sekretaris Desa"),
    "id_wajah": fields.Integer(description="null -> wajah belum didaftarkan, belum bisa absen"),
    "foto_wajah_url": fields.String(example="/api/pegawai/2/wajah/foto?v=7"),
})

login_absensi_result_model = ns.clone("LoginAbsensiResult", login_result_model, {
    "pegawai": fields.Nested(pegawai_login_model),
})


@ns.route("/login")
class Login(Resource):
    @ns.expect(login_model, validate=True)
    @ns.doc(security=[])
    @ns.response(200, "Login berhasil", docs.envelope(ns, login_result_model))
    # @docs.errors(ns, 400, 401)
    def post(self):
        """(publik) Login panel admin

        Tanpa token. Semua akun aktif bisa login; JWT berisi `app: "ADMIN"`.
        Endpoint (admin) hanya menerima token dari login ini.
        Error `LOGIN_GAGAL` (401) bila username/password salah.
        """
        p = request.get_json()
        return {"data": service.login(p["username"], p["password"])}


@ns.route("/login-absensi")
class LoginAbsensi(Resource):
    @ns.expect(login_model, validate=True)
    @ns.doc(security=[])
    @ns.response(200, "Login berhasil", docs.envelope(ns, login_absensi_result_model))
    def post(self):
        """(publik) Login aplikasi absensi pegawai

        Tanpa token. Username & password sama dengan akun user, tapi hanya akun yang tertaut ke
        pegawai aktif yang bisa login. JWT berisi `app: "ABSENSI"`: bisa dipakai untuk endpoint
        (pegawai) & (pegawai & admin), ditolak 403 `AKSES_DITOLAK` di endpoint (admin).
        Error: `LOGIN_GAGAL` (401), `BUKAN_PEGAWAI` (403).
        """
        p = request.get_json()
        return {"data": service.login_absensi(p["username"], p["password"])}


@ns.route("/me")
class Me(Resource):
    @roles_required()
    @ns.response(200, "OK", docs.envelope(ns, user_model))
    # @docs.errors(ns, 401, 404)
    def get(self):
        """(pegawai & admin) Data akun yang sedang login

        Role: semua user yang login.
        """
        return {"data": service.get_me(current_user_id())}


@ns.route("/ganti-password")
class GantiPassword(Resource):
    @roles_required()
    @ns.expect(ganti_password_model, validate=True)
    @ns.response(200, "Password berhasil diubah", docs.message(ns))
    # @docs.errors(ns, 400, 401)
    def post(self):
        """(pegawai & admin) Ganti password akun sendiri

        Role: semua user yang login.
        Error: `PASSWORD_TERLALU_PENDEK`, `PASSWORD_LAMA_SALAH` (400).
        """
        p = request.get_json()
        service.ganti_password(current_user_id(), p["password_lama"], p["password_baru"])
        return {"data": {"message": "Password berhasil diubah"}}
