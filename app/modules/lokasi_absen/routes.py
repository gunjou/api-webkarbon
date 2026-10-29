from flask import request
from flask_restx import Namespace, Resource, fields

from app.core import docs
from app.core.auth import ADMIN, KADES, OPERATOR, current_user_id, roles_required

from . import service

ns = Namespace("Lokasi Absen", description="Lokasi absen (titik pusat + radius geofence)")

lokasi_model = ns.model("LokasiAbsen", {
    "nama": fields.String(required=True, example="Kantor Desa"),
    "latitude": fields.Float(required=True, example=-8.62, description="-90 s/d 90"),
    "longitude": fields.Float(required=True, example=116.1, description="-180 s/d 180"),
    "radius_meter": fields.Integer(default=100, description="10 s/d 1000 meter"),
})

lokasi_out = ns.clone("LokasiAbsenDetail", {"id_lokasi": fields.Integer(example=1)}, lokasi_model, {
    "created_at": fields.DateTime,
    "updated_at": fields.DateTime,
})


@ns.route("")
class LokasiList(Resource):
    @roles_required(ADMIN, OPERATOR, KADES)
    @ns.param("q", "Cari nama lokasi")
    @ns.response(200, "OK", docs.envelope_list(ns, lokasi_out))
    # @docs.errors(ns, 401, 403)
    def get(self):
        """(admin) Daftar lokasi absen (geofence)

        Role: ADMIN, OPERATOR, KADES. Urut nama.
        """
        return {"data": service.list_lokasi(request.args.get("q"))}

    @roles_required(ADMIN)
    @ns.expect(lokasi_model)
    @ns.response(201, "Lokasi ditambahkan", docs.envelope(ns, lokasi_out))
    # @docs.errors(ns, 400, 401, 403)
    def post(self):
        """(admin) Tambah lokasi absen

        Role: ADMIN. Dicatat di audit log.
        Error: `FIELD_WAJIB_KOSONG`, `KOORDINAT_TIDAK_VALID`, `RADIUS_TIDAK_VALID` (400),
        `LOKASI_SUDAH_ADA` (409).
        """
        return {"data": service.tambah_lokasi(request.get_json(), current_user_id())}, 201


@ns.route("/<int:id_lokasi>")
@ns.param("id_lokasi", "ID lokasi absen")
class LokasiItem(Resource):
    @roles_required(ADMIN, OPERATOR, KADES)
    @ns.response(200, "OK", docs.envelope(ns, lokasi_out))
    # @docs.errors(ns, 401, 403, 404)
    def get(self, id_lokasi):
        """(admin) Detail lokasi absen

        Role: ADMIN, OPERATOR, KADES.
        """
        return {"data": service.detail_lokasi(id_lokasi)}

    @roles_required(ADMIN)
    @ns.expect(lokasi_model)
    @ns.response(200, "Lokasi diubah", docs.envelope(ns, lokasi_out))
    # @docs.errors(ns, 400, 401, 403, 404)
    def put(self, id_lokasi):
        """(admin) Ubah lokasi absen

        Role: ADMIN. Semua field dikirim ulang. Perubahan dicatat di audit log.
        Error: `FIELD_WAJIB_KOSONG`, `KOORDINAT_TIDAK_VALID`, `RADIUS_TIDAK_VALID` (400),
        `LOKASI_TIDAK_DITEMUKAN` (404), `LOKASI_SUDAH_ADA` (409).
        """
        return {"data": service.ubah_lokasi(id_lokasi, request.get_json(), current_user_id())}

    @roles_required(ADMIN)
    @ns.response(200, "Lokasi dihapus", docs.message(ns))
    # @docs.errors(ns, 401, 403, 404)
    def delete(self, id_lokasi):
        """(admin) Hapus lokasi absen (soft delete)

        Role: ADMIN. Perubahan dicatat di audit log.
        """
        service.hapus_lokasi(id_lokasi, current_user_id())
        return {"data": {"message": "Lokasi absen dihapus"}}
