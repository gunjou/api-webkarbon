from flask import request
from flask_restx import Namespace, Resource, fields

from app.core import docs
from app.core.auth import ADMIN, KADES, OPERATOR, current_user_id, roles_required

from . import service

ns = Namespace("Persuratan", description="Jenis surat, draft, finalisasi, register surat")

subjek_model = ns.model("SubjekSurat", {
    "nik": fields.String(required=True),
    "nama": fields.String(required=True),
    "tempat_lahir": fields.String(required=True),
    "tgl_lahir": fields.Date(required=True),
    "jenis_kelamin": fields.String(required=True, enum=["L", "P"]),
    "agama": fields.String,
    "status_kawin": fields.String,
    "pekerjaan": fields.String,
    "kewarganegaraan": fields.String(default="Indonesia"),
    "alamat_lengkap": fields.String(required=True),
})

draft_model = ns.model("DraftSurat", {
    "id_jenis_surat": fields.Integer(required=True),
    "id_penduduk": fields.Integer(description="Opsi A: penduduk terdaftar"),
    "subjek": fields.Nested(subjek_model, description="Opsi B: penduduk belum terdaftar"),
    "abaikan_nik_terdaftar": fields.Boolean(default=False),
    "keperluan": fields.String(example="pengajuan pinjaman di Bank"),
    "isian": fields.Raw(description="Field khusus sesuai field_schema jenis surat"),
    "id_penandatangan": fields.Integer,
})

jenis_surat_model = ns.model("JenisSurat", {
    "id_jenis_surat": fields.Integer(example=1),
    "kode": fields.String(example="SK_BELUM_MENIKAH"),
    "nama": fields.String(example="Surat Keterangan Belum Menikah"),
    "judul_surat": fields.String(example="SURAT KETERANGAN BELUM MENIKAH"),
    "kode_klasifikasi": fields.String(example="148.1"),
    "pakai_subjek": fields.Boolean,
    "field_schema": fields.List(fields.Raw, description="Definisi field isian: name, label, type, "
                                                        "required, options"),
})

penandatangan_model = ns.model("Penandatangan", {
    "id_penandatangan": fields.Integer(example=1),
    "id_pegawai": fields.Integer,
    "nama": fields.String,
    "jabatan_label": fields.String(example="Sekretaris Desa"),
    "mode": fields.String(enum=["LANGSUNG", "AN"]),
    "is_default": fields.Boolean,
})

surat_data_model = ns.model("DataSurat", {
    "subjek": fields.Nested(subjek_model, allow_null=True,
                            description="Snapshot data diri; null bila jenis surat tanpa subjek"),
    "keperluan": fields.String,
    "isian": fields.Raw,
})

surat_ringkas_model = ns.model("SuratRingkas", {
    "id_surat": fields.Integer(example=1),
    "nama_jenis": fields.String,
    "status_surat": fields.String(enum=["DRAFT", "FINAL", "BATAL"]),
    "nomor_surat": fields.String,
    "tanggal_surat": fields.Date,
    "nik": fields.String,
    "nama": fields.String,
    "keperluan": fields.String,
    "created_at": fields.DateTime,
})

surat_detail_model = ns.model("SuratDetail", {
    "id_surat": fields.Integer(example=1),
    "id_jenis_surat": fields.Integer,
    "nama_jenis": fields.String,
    "kode_jenis": fields.String,
    "status_surat": fields.String(enum=["DRAFT", "FINAL", "BATAL"]),
    "id_penduduk": fields.Integer,
    "data": fields.Nested(surat_data_model),
    "id_penandatangan": fields.Integer,
    "penandatangan": fields.Raw(description="Snapshot penandatangan saat finalisasi"),
    "nomor_urut": fields.Integer,
    "nomor_surat": fields.String,
    "tanggal_surat": fields.Date,
    "file_pdf": fields.String,
    "alasan_batal": fields.String,
    "created_by": fields.Integer,
    "created_at": fields.DateTime,
    "updated_at": fields.DateTime,
    "finalized_by": fields.Integer,
    "finalized_at": fields.DateTime,
    "dibatalkan_by": fields.Integer,
    "dibatalkan_at": fields.DateTime,
})

SEMUA = (ADMIN, OPERATOR, KADES)


@ns.route("/jenis-surat")
class JenisSuratList(Resource):
    @roles_required(*SEMUA)
    @ns.response(200, "OK", docs.envelope_list(ns, jenis_surat_model))
    # @docs.errors(ns, 401, 403)
    def get(self):
        """(admin) Daftar jenis surat

        Role: ADMIN, OPERATOR, KADES.
        """
        return {"data": service.list_jenis_surat()}


@ns.route("/penandatangan")
class PenandatanganList(Resource):
    @roles_required(*SEMUA)
    @ns.response(200, "OK", docs.envelope_list(ns, penandatangan_model))
    # @docs.errors(ns, 401, 403)
    def get(self):
        """(admin) Daftar penandatangan surat

        Role: ADMIN, OPERATOR, KADES.
        """
        return {"data": service.list_penandatangan()}


@ns.route("/surat")
class SuratList(Resource):
    @roles_required(*SEMUA)
    @ns.param("id_jenis_surat", "Filter jenis surat", type=int)
    @ns.param("status_surat", "DRAFT / FINAL / BATAL", enum=["DRAFT", "FINAL", "BATAL"])
    @ns.param("tahun", "Tahun surat", type=int)
    @ns.param("q", "Cari nomor surat, NIK, atau nama")
    @ns.param("page", "Halaman", default=1)
    @ns.param("per_page", "Jumlah per halaman (maks 100)", default=20)
    @ns.response(200, "OK", docs.paginated(ns, surat_ringkas_model))
    # @docs.errors(ns, 401, 403)
    def get(self):
        """(admin) Register surat (paginasi)

        Role: ADMIN, OPERATOR, KADES.
        """
        return {"data": service.list_surat(request.args)}

    @roles_required(ADMIN, OPERATOR)
    @ns.expect(draft_model)
    @ns.response(201, "Draft dibuat", docs.envelope(ns, surat_detail_model))
    # @docs.errors(ns, 400, 401, 403, 404, 409)
    def post(self):
        """(admin) Buat draft surat

        Role: ADMIN, OPERATOR.

        Subjek: isi `id_penduduk` (opsi A, penduduk terdaftar) **atau** `subjek` (opsi B,
        penduduk belum terdaftar). Opsi B dengan NIK yang sudah terdaftar ditolak 409
        `NIK_SUDAH_TERDAFTAR`, kecuali `abaikan_nik_terdaftar: true`.
        `isian` divalidasi terhadap `field_schema` jenis surat (`ISIAN_TIDAK_LENGKAP`,
        `ISIAN_TIDAK_VALID`).
        """
        return {"data": service.buat_draft(request.get_json(), current_user_id())}, 201


@ns.route("/surat/<int:id_surat>")
@ns.param("id_surat", "ID surat")
class SuratItem(Resource):
    @roles_required(*SEMUA)
    @ns.response(200, "OK", docs.envelope(ns, surat_detail_model))
    # @docs.errors(ns, 401, 403, 404)
    def get(self, id_surat):
        """(admin) Detail surat

        Role: ADMIN, OPERATOR, KADES.
        """
        return {"data": service.detail_surat(id_surat)}

    @roles_required(ADMIN, OPERATOR)
    @ns.expect(draft_model)
    @ns.response(200, "Draft diubah", docs.envelope(ns, surat_detail_model))
    # @docs.errors(ns, 400, 401, 403, 404, 409)
    def put(self, id_surat):
        """(admin) Ubah draft surat

        Role: ADMIN, OPERATOR. Hanya surat berstatus DRAFT
        (selain itu 409 `SURAT_SUDAH_FINAL`). `id_jenis_surat` tidak bisa diganti.
        """
        return {"data": service.ubah_draft(id_surat, request.get_json(), current_user_id())}


# Berikutnya:
#   GET  /surat/<id>/preview      -> PDF stream (tanpa nomor, tidak disimpan)
#   POST /surat/<id>/finalisasi   -> terbitkan nomor + simpan PDF
#   GET  /surat/<id>/pdf          -> unduh PDF final
#   POST /surat/<id>/batal        -> wajib alasan
#   GET  /register/export         -> xlsx buku register
