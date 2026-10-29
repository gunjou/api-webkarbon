"""
Manajemen user/admin.

Membuat admin pertama saat tabel users masih kosong: comment baris @roles_required(ADMIN)
di endpoint yang dibutuhkan (minimal POST /users), buat admin, lalu aktifkan kembali.
Pelaku (created_by / audit) diambil lewat optional_user_id(), jadi tetap aman tanpa token.
"""
from flask import request
from flask_restx import Namespace, Resource, fields

from app.core import docs
from app.core.auth import ADMIN, optional_user_id, roles_required

from . import service

ns = Namespace("Users", description="Manajemen Users (ADMIN, OPERATOR, PEGAWAI, KADES)")

ROLE_ENUM = ["ADMIN", "OPERATOR", "PEGAWAI", "KADES"]

user_input_model = ns.model("UserInput", {
    "username": fields.String(required=True, example="admin",
                              description="3-50 karakter: huruf, angka, titik, underscore"),
    "nama": fields.String(required=True, example="Administrator"),
    "role": fields.String(enum=ROLE_ENUM, default="ADMIN"),
    "id_pegawai": fields.Integer(description="Wajib untuk role PEGAWAI"),
})

user_create_model = ns.clone("UserCreate", user_input_model, {
    "password": fields.String(required=True, example="rahasia123", description="Minimal 5 karakter"),
})

reset_password_model = ns.model("ResetPassword", {
    "password_baru": fields.String(required=True, description="Minimal 5 karakter"),
})

user_out = ns.model("UserDetail", {
    "id_user": fields.Integer(example=1),
    "username": fields.String(example="admin"),
    "nama": fields.String(example="Administrator"),
    "role": fields.String(enum=ROLE_ENUM),
    "id_pegawai": fields.Integer,
    "nama_pegawai": fields.String,
    "id_wajah": fields.Integer(description="Wajah pegawai tertaut; null kalau bukan pegawai / belum punya wajah"),
    "foto_wajah_url": fields.String(example="/api/pegawai/2/wajah/foto?v=7",
                                    description="GET dengan header Authorization; null kalau bukan pegawai / belum punya wajah"),
    "last_login_at": fields.DateTime,
    "created_at": fields.DateTime,
    "updated_at": fields.DateTime,
})


@ns.route("")
class UserList(Resource):
    @roles_required(ADMIN)
    @ns.param("q", "Cari username / nama")
    @ns.param("role", "Filter role", enum=ROLE_ENUM)
    @ns.response(200, "OK", docs.envelope_list(ns, user_out))
    # @docs.errors(ns, 401, 403)
    def get(self):
        """(admin) Daftar user

        Role: ADMIN.
        """
        return {"data": service.list_users(request.args.get("q"), request.args.get("role"))}

    @roles_required(ADMIN)  # comment baris ini untuk membuat admin pertama tanpa token
    @ns.expect(user_create_model)
    @ns.response(201, "User dibuat", docs.envelope(ns, user_out))
    # @docs.errors(ns, 400, 401, 403, 404, 409)
    def post(self):
        """(admin) Buat user / admin baru

        Role: ADMIN. `role` default `ADMIN`.
        Error: `USERNAME_TIDAK_VALID`, `ROLE_TIDAK_VALID`, `PASSWORD_TERLALU_PENDEK`,
        `PEGAWAI_WAJIB_DIISI` (400), `USERNAME_SUDAH_DIPAKAI`, `PEGAWAI_SUDAH_PUNYA_AKUN` (409).
        """
        return {"data": service.tambah_user(request.get_json(silent=True), optional_user_id())}, 201


@ns.route("/<int:id_user>")
@ns.param("id_user", "ID user")
class UserItem(Resource):
    @roles_required(ADMIN)
    @ns.response(200, "OK", docs.envelope(ns, user_out))
    # @docs.errors(ns, 401, 403, 404)
    def get(self, id_user):
        """(admin) Detail user

        Role: ADMIN.
        """
        return {"data": service.detail_user(id_user)}

    @roles_required(ADMIN)
    @ns.expect(user_input_model)
    @ns.response(200, "User diubah", docs.envelope(ns, user_out))
    # @docs.errors(ns, 400, 401, 403, 404, 409)
    def put(self, id_user):
        """(admin) Ubah data user (tanpa password)

        Role: ADMIN. Admin aktif terakhir tidak bisa diturunkan role-nya (409 `ADMIN_TERAKHIR`).
        Perubahan dicatat di audit log.
        """
        return {"data": service.ubah_user(id_user, request.get_json(silent=True), optional_user_id())}

    @roles_required(ADMIN)
    @ns.response(200, "User dihapus", docs.message(ns))
    # @docs.errors(ns, 401, 403, 404, 409)
    def delete(self, id_user):
        """(admin) Hapus user (soft delete)

        Role: ADMIN. Tidak bisa menghapus akun sendiri (`HAPUS_DIRI_SENDIRI`) atau
        admin aktif terakhir (`ADMIN_TERAKHIR`).
        """
        service.hapus_user(id_user, optional_user_id())
        return {"data": {"message": "User dihapus"}}


@ns.route("/<int:id_user>/reset-password")
@ns.param("id_user", "ID user")
class UserResetPassword(Resource):
    @roles_required(ADMIN)
    @ns.expect(reset_password_model)
    @ns.response(200, "Password direset", docs.message(ns))
    # @docs.errors(ns, 400, 401, 403, 404)
    def put(self, id_user):
        """(admin) Reset password user

        Role: ADMIN. Tidak perlu password lama.
        """
        service.reset_password(id_user, (request.get_json(silent=True) or {}).get("password_baru"),
                               optional_user_id())
        return {"data": {"message": "Password berhasil direset"}}
