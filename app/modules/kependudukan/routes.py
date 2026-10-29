from flask import request
from flask_restx import Namespace, Resource, fields

from app.core import docs
from app.core.auth import ADMIN, KADES, OPERATOR, current_user_id, roles_required

from . import service

ns = Namespace("Penduduk", description="Master data penduduk")

penduduk_model = ns.model("Penduduk", {
    "nik": fields.String(required=True, example="5201xxxxxxxxxxxx", description="16 digit angka"),
    "nama": fields.String(required=True),
    "no_kk": fields.String(description="16 digit angka"),
    "tempat_lahir": fields.String,
    "tgl_lahir": fields.Date,
    "jenis_kelamin": fields.String(enum=["L", "P"]),
    "agama": fields.String,
    "status_kawin": fields.String,
    "pekerjaan": fields.String,
    "kewarganegaraan": fields.String(default="Indonesia"),
    "alamat": fields.String,
    "dusun": fields.String,
    "rt": fields.String,
    "rw": fields.String,
})

penduduk_out = ns.clone("PendudukDetail", {"id_penduduk": fields.Integer(example=1)}, penduduk_model)


@ns.route("")
class PendudukList(Resource):
    @roles_required(ADMIN, OPERATOR, KADES)
    @ns.param("q", "Cari NIK (awalan) atau nama")
    @ns.param("dusun", "Filter dusun")
    @ns.param("page", "Halaman", default=1)
    @ns.param("per_page", "Jumlah per halaman (maks 100)", default=20)
    @ns.response(200, "OK", docs.paginated(ns, penduduk_out))
    # @docs.errors(ns, 401, 403)
    def get(self):
        """(admin) Daftar penduduk (paginasi)

        Role: ADMIN, OPERATOR, KADES.
        """
        a = request.args
        return {"data": service.list_penduduk(a.get("q"), a.get("dusun"),
                                              a.get("page", 1), a.get("per_page", 20))}

    @roles_required(ADMIN, OPERATOR)
    @ns.expect(penduduk_model)
    @ns.response(201, "Penduduk ditambahkan", docs.envelope(ns, penduduk_out))
    # @docs.errors(ns, 400, 401, 403, 409)
    def post(self):
        """(admin) Tambah penduduk

        Role: ADMIN, OPERATOR.
        Error: `NIK_TIDAK_VALID`, `JENIS_KELAMIN_TIDAK_VALID` (400),
        `NIK_SUDAH_TERDAFTAR` (409, `details.id_penduduk` berisi data yang sudah ada).
        """
        return {"data": service.tambah_penduduk(request.get_json(), current_user_id())}, 201


@ns.route("/<int:id_penduduk>")
@ns.param("id_penduduk", "ID penduduk")
class PendudukItem(Resource):
    @roles_required(ADMIN, OPERATOR, KADES)
    @ns.response(200, "OK", docs.envelope(ns, penduduk_out))
    # @docs.errors(ns, 401, 403, 404)
    def get(self, id_penduduk):
        """(admin) Detail penduduk

        Role: ADMIN, OPERATOR, KADES.
        """
        return {"data": service.detail_penduduk(id_penduduk)}

    @roles_required(ADMIN, OPERATOR)
    @ns.expect(penduduk_model)
    @ns.response(200, "Penduduk diubah", docs.envelope(ns, penduduk_out))
    # @docs.errors(ns, 400, 401, 403, 404, 409)
    def put(self, id_penduduk):
        """(admin) Ubah penduduk

        Role: ADMIN, OPERATOR. Perubahan dicatat di audit log.
        """
        return {"data": service.ubah_penduduk(id_penduduk, request.get_json(), current_user_id())}

    @roles_required(ADMIN)
    @ns.response(200, "Penduduk dihapus", docs.message(ns))
    # @docs.errors(ns, 401, 403, 404)
    def delete(self, id_penduduk):
        """(admin) Hapus penduduk (soft delete)

        Role: ADMIN. Perubahan dicatat di audit log.
        """
        service.hapus_penduduk(id_penduduk, current_user_id())
        return {"data": {"message": "Data penduduk dihapus"}}
