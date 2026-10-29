from flask import request, send_file
from flask_restx import Namespace, Resource, fields
from werkzeug.datastructures import FileStorage

from app.core import docs
from app.core.auth import ADMIN, KADES, OPERATOR, current_pegawai_id, current_user_id, roles_required

from . import service

ns = Namespace("Pegawai", description="Data perangkat desa / pegawai")

pegawai_model = ns.model("Pegawai", {
    "nama": fields.String(required=True),
    "jabatan": fields.String(required=True, example="Sekretaris Desa"),
    "nik": fields.String,
    "no_hp": fields.String,
    "tanggal_mulai": fields.Date,
})

pegawai_out = ns.clone("PegawaiDetail", {"id_pegawai": fields.Integer(example=1)}, pegawai_model, {
    "created_at": fields.DateTime,
    "updated_at": fields.DateTime,
    "id_wajah": fields.Integer(description="Satu foto wajah aktif, null kalau belum enroll"),
    "foto_wajah_url": fields.String(example="/api/pegawai/1/wajah/foto?v=7",
                                    description="GET dengan header Authorization, null kalau belum enroll"),
})

akun_input_model = ns.model("PegawaiAkunInput", {
    "username": fields.String(required=True, example="kaharudin",
                              description="3-50 karakter: huruf, angka, titik, underscore"),
    "password": fields.String(required=True, example="rahasia123", description="Minimal 5 karakter"),
    "role": fields.String(enum=["ADMIN", "OPERATOR", "PEGAWAI", "KADES"], default="PEGAWAI"),
    "nama": fields.String(description="Default: nama pegawai"),
})

pegawai_create_model = ns.clone("PegawaiCreate", pegawai_model, {
    "akun": fields.Nested(akun_input_model, description="Opsional. Isi untuk sekalian membuat user login"),
})

akun_out = ns.model("PegawaiAkun", {
    "id_user": fields.Integer(example=5),
    "username": fields.String(example="kaharudin"),
    "nama": fields.String,
    "role": fields.String,
    "id_pegawai": fields.Integer,
})

pegawai_create_out = ns.clone("PegawaiCreateDetail", pegawai_out, {
    "akun": fields.Nested(akun_out, allow_null=True),
})


@ns.route("")
class PegawaiList(Resource):
    @roles_required(ADMIN, OPERATOR, KADES)
    @ns.param("q", "Cari nama / jabatan")
    @ns.response(200, "OK", docs.envelope_list(ns, pegawai_out))
    # @docs.errors(ns, 401, 403)
    def get(self):
        """(admin) Daftar pegawai

        Role: ADMIN, OPERATOR, KADES.
        """
        return {"data": service.list_pegawai(request.args.get("q"))}

    @roles_required(ADMIN)
    @ns.expect(pegawai_create_model)
    @ns.response(201, "Pegawai ditambahkan", docs.envelope(ns, pegawai_create_out))
    # @docs.errors(ns, 400, 401, 403, 409)
    def post(self):
        """(admin) Tambah pegawai (opsional sekaligus user login)

        Role: ADMIN. Isi `akun` untuk membuat user login dalam satu transaksi
        (role default `PEGAWAI`, nama default = nama pegawai). Kalau pembuatan akun gagal,
        pegawai juga batal dibuat.
        Error: `FIELD_WAJIB_KOSONG`, `AKUN_TIDAK_VALID`, `USERNAME_TIDAK_VALID`,
        `PASSWORD_TERLALU_PENDEK` (400), `USERNAME_SUDAH_DIPAKAI` (409).
        """
        return {"data": service.tambah_pegawai(request.get_json(), current_user_id())}, 201


pegawai_saya_out = ns.clone("PegawaiSaya", pegawai_out, {
    "wajah_terdaftar": fields.Boolean(description="false = belum bisa absen, minta admin enroll wajah"),
})


@ns.route("/me")
class PegawaiSaya(Resource):
    @roles_required()
    @ns.response(200, "OK", docs.envelope(ns, pegawai_saya_out))
    def get(self):
        """(pegawai) Data diri pegawai yang login

        Semua role yang akunnya tertaut ke pegawai.
        Error: `BUKAN_PEGAWAI` (403), `PEGAWAI_TIDAK_DITEMUKAN` (404).
        """
        return {"data": service.pegawai_saya(current_pegawai_id())}


@ns.route("/me/wajah/foto")
class PegawaiSayaWajahFoto(Resource):
    @roles_required()
    @ns.produces(["image/jpeg"])
    @ns.response(200, "File JPEG")
    def get(self):
        """(pegawai) Foto wajah terdaftar milik saya (image/jpeg)

        Pakai `foto_wajah_url` dari GET /pegawai/me.
        Error: `BUKAN_PEGAWAI` (403), `WAJAH_TIDAK_DITEMUKAN`, `FILE_TIDAK_DITEMUKAN` (404).
        """
        return send_file(service.path_foto_wajah(current_pegawai_id()), mimetype="image/jpeg", max_age=86400)


@ns.route("/<int:id_pegawai>")
@ns.param("id_pegawai", "ID pegawai")
class PegawaiItem(Resource):
    @roles_required(ADMIN, OPERATOR, KADES)
    @ns.response(200, "OK", docs.envelope(ns, pegawai_out))
    # @docs.errors(ns, 401, 403, 404)
    def get(self, id_pegawai):
        """(admin) Detail pegawai

        Role: ADMIN, OPERATOR, KADES.
        """
        return {"data": service.detail_pegawai(id_pegawai)}

    @roles_required(ADMIN)
    @ns.expect(pegawai_model)
    @ns.response(200, "Pegawai diubah", docs.envelope(ns, pegawai_out))
    # @docs.errors(ns, 400, 401, 403, 404, 409)
    def put(self, id_pegawai):
        """(admin) Ubah pegawai

        Role: ADMIN. Perubahan dicatat di audit log.
        """
        return {"data": service.ubah_pegawai(id_pegawai, request.get_json(), current_user_id())}

    @roles_required(ADMIN)
    @ns.response(200, "Pegawai dihapus", docs.message(ns))
    # @docs.errors(ns, 401, 403, 404)
    def delete(self, id_pegawai):
        """(admin) Hapus pegawai (soft delete)

        Role: ADMIN. Perubahan dicatat di audit log.
        """
        service.hapus_pegawai(id_pegawai, current_user_id())
        return {"data": {"message": "Pegawai dihapus"}}


# ---------- wajah pegawai (1 wajah aktif per pegawai) ----------

wajah_out = ns.model("WajahPegawai", {
    "id_wajah": fields.Integer(example=7),
    "id_pegawai": fields.Integer(example=1),
    "foto_path": fields.String(example="wajah/2026/10/ab12cd.jpg"),
    "foto_url": fields.String(example="/api/pegawai/1/wajah/foto?v=7",
                              description="GET dengan header Authorization untuk menampilkan foto"),
    "created_at": fields.DateTime,
})

upload_foto = ns.parser()
upload_foto.add_argument("foto", location="files", type=FileStorage, required=True,
                         help="1 foto JPG/PNG, satu wajah")


@ns.route("/<int:id_pegawai>/wajah")
@ns.param("id_pegawai", "ID pegawai")
class PegawaiWajah(Resource):
    @roles_required(ADMIN)
    @ns.expect(upload_foto)
    @ns.response(201, "Wajah ditambahkan", docs.envelope(ns, wajah_out))
    @ns.response(200, "Wajah diganti", docs.envelope(ns, wajah_out))
    # @docs.errors(ns, 400, 401, 403, 404)
    def put(self, id_pegawai):
        """(admin) Simpan wajah pegawai (tambah / ganti)

        Role: ADMIN. multipart/form-data, field `foto`. Satu pegawai hanya punya 1 wajah:
        kalau sudah ada, foto lama diganti (200); kalau belum, ditambahkan (201).
        Wajah otomatis di-crop & dikompres (300x300 JPEG). Dicatat di audit log.
        Error: `FILE_KOSONG`, `FOTO_TIDAK_VALID`, `WAJAH_TIDAK_TERDETEKSI`, `WAJAH_LEBIH_DARI_SATU` (400),
        `PEGAWAI_TIDAK_DITEMUKAN` (404).
        """
        wajah, dibuat = service.simpan_wajah(id_pegawai, request.files.get("foto"), current_user_id())
        return {"data": wajah}, 201 if dibuat else 200

    @roles_required(ADMIN)
    @ns.response(200, "Wajah dihapus", docs.message(ns))
    # @docs.errors(ns, 401, 403, 404)
    def delete(self, id_pegawai):
        """(admin) Hapus wajah pegawai

        Role: ADMIN. Pegawai harus didaftarkan wajahnya lagi sebelum bisa absen. Dicatat di audit log.
        Error: `PEGAWAI_TIDAK_DITEMUKAN`, `WAJAH_TIDAK_DITEMUKAN` (404).
        """
        service.hapus_wajah(id_pegawai, current_user_id())
        return {"data": {"message": "Foto wajah dihapus"}}


@ns.route("/<int:id_pegawai>/wajah/foto")
@ns.param("id_pegawai", "ID pegawai")
class PegawaiWajahFoto(Resource):
    @roles_required(ADMIN, OPERATOR, KADES)
    @ns.produces(["image/jpeg"])
    @ns.response(200, "File JPEG")
    # @docs.errors(ns, 401, 403, 404)
    def get(self, id_pegawai):
        """(admin) File foto wajah pegawai (image/jpeg)

        Role: ADMIN, OPERATOR, KADES. Pakai `foto_wajah_url` dari data pegawai (sudah berisi ?v=
        untuk cache-busting).
        """
        return send_file(service.path_foto_wajah(id_pegawai), mimetype="image/jpeg", max_age=86400)
