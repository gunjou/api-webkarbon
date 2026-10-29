from flask import request
from flask_restx import Namespace, Resource, fields

from app.core import docs
from app.core.audit import catat_audit
from app.core.auth import ADMIN, KADES, OPERATOR, current_user_id, roles_required
from app.core.db import get_connection, now_wita
from app.core.errors import AppError

from . import queries as q

ns = Namespace("Pengaturan", description="Konfigurasi desa, format nomor, jadwal kerja, absensi")

pengaturan_model = ns.model("Pengaturan", {
    "key": fields.String(example="desa"),
    "value": fields.Raw(description="Nilai JSON bebas (object / array / string / angka)",
                        example={"nama": "Contoh", "kecamatan": "Contoh", "kabupaten": "Contoh"}),
    "updated_by": fields.Integer,
    "updated_at": fields.DateTime,
})

pengaturan_value_model = ns.model("PengaturanValue", {
    "key": fields.String(example="desa"),
    "value": fields.Raw(example={"nama": "Contoh"}),
})

pengaturan_input_model = ns.model("PengaturanInput", {
    "value": fields.Raw(required=True, description="Nilai JSON baru untuk key ini",
                        example={"nama": "Contoh"}),
})


@ns.route("")
class PengaturanList(Resource):
    @roles_required(ADMIN, OPERATOR, KADES)
    @ns.response(200, "OK", docs.envelope_list(ns, pengaturan_model))
    # @docs.errors(ns, 401, 403)
    def get(self):
        """(admin) Semua pengaturan

        Role: ADMIN, OPERATOR, KADES.
        """
        with get_connection().connect() as conn:
            return {"data": q.get_all(conn)}


@ns.route("/<string:key>")
@ns.param("key", "Key pengaturan, mis. `desa`")
class PengaturanItem(Resource):
    @roles_required()
    @ns.response(200, "OK", docs.envelope(ns, pengaturan_value_model))
    # @docs.errors(ns, 401, 404)
    def get(self, key):
        """(pegawai & admin) Ambil satu pengaturan

        Role: semua user yang login.
        """
        with get_connection().connect() as conn:
            value = q.get_pengaturan(conn, key)
        if value is None:
            raise AppError("PENGATURAN_TIDAK_DITEMUKAN", f"Pengaturan '{key}' tidak ditemukan", 404)
        return {"data": {"key": key, "value": value}}

    @roles_required(ADMIN)
    @ns.expect(pengaturan_input_model)
    @ns.response(200, "Pengaturan disimpan", docs.envelope(ns, pengaturan_value_model))
    # @docs.errors(ns, 400, 401, 403)
    def put(self, key):
        """(admin) Simpan pengaturan (buat baru / timpa)

        Role: ADMIN. Perubahan dicatat di audit log.
        """
        value = (request.get_json(silent=True) or {}).get("value")
        if value is None:
            raise AppError("FIELD_WAJIB_KOSONG", "Field 'value' wajib diisi", 400)

        with get_connection().begin() as conn:
            lama = q.get_pengaturan(conn, key)
            q.upsert(conn, key, value, current_user_id(), now_wita())
            catat_audit(conn, current_user_id(), "UBAH_PENGATURAN", "pengaturan",
                        data_lama={"key": key, "value": lama}, data_baru={"key": key, "value": value})
        return {"data": {"key": key, "value": value}}
