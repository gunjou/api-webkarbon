"""
Endpoint perizinan (IZIN / SAKIT / CUTI / DINAS).

Pegawai (akun tertaut pegawai, aplikasi absen):
  POST "" ajukan, GET /saya, POST /{id}/batal (miliknya, masih PENDING)
Admin:
  ADMIN, OPERATOR, KADES -> baca semua (list, detail, lampiran)
  ADMIN, KADES           -> setujui / tolak / batalkan izin yang sudah disetujui
"""
from flask import request, send_file
from flask_restx import Namespace, Resource, fields
from werkzeug.datastructures import FileStorage

from app.core import docs
from app.core.auth import (ADMIN, APP_ADMIN, KADES, OPERATOR, current_app_token, current_pegawai_id,
                           current_role, current_user_id, roles_required)
from app.core.errors import AppError

from . import service

ns = Namespace("Perizinan", description=(
    "Pengajuan izin, sakit, cuti, perjalanan dinas & persetujuannya. "
    "Label: (pegawai) = aplikasi absen, data milik sendiri; (admin) = panel admin; "
    "(pegawai & admin) = dipakai keduanya, pegawai hanya melihat data miliknya."))

MONITOR = (ADMIN, OPERATOR, KADES)
PEMROSES = (ADMIN, KADES)


def _admin():
    return current_role() in MONITOR and current_app_token() == APP_ADMIN


def _pemilik():
    """Panel admin melihat semua; selain itu hanya izin milik sendiri."""
    return None if _admin() else current_pegawai_id()


# ---------- parser (Swagger) ----------

ajukan_parser = ns.parser()
ajukan_parser.add_argument("jenis", location="form", required=True, choices=service.JENIS)
ajukan_parser.add_argument("tanggal_mulai", location="form", required=True, help="YYYY-MM-DD")
ajukan_parser.add_argument("tanggal_selesai", location="form", required=True, help="YYYY-MM-DD")
ajukan_parser.add_argument("alasan", location="form", required=True)
ajukan_parser.add_argument("lampiran", location="files", type=FileStorage,
                           help="JPG/PNG/PDF. Wajib untuk SAKIT (surat dokter), mis. surat tugas untuk DINAS")

saya_parser = ns.parser()
saya_parser.add_argument("tanggal_mulai", location="args", help="YYYY-MM-DD")
saya_parser.add_argument("tanggal_selesai", location="args", help="YYYY-MM-DD")
saya_parser.add_argument("jenis", location="args", choices=service.JENIS)
saya_parser.add_argument("status", location="args", choices=service.STATUS)
saya_parser.add_argument("page", location="args", type=int, default=1)
saya_parser.add_argument("per_page", location="args", type=int, default=20, help="Maks 100")

list_parser = saya_parser.copy()
list_parser.add_argument("id_pegawai", location="args", type=int)

# ---------- model ----------

izin_out = ns.model("Izin", {
    "id_izin": fields.Integer(example=1),
    "id_pegawai": fields.Integer(example=2),
    "nama_pegawai": fields.String(example="Kaharudin"),
    "jabatan": fields.String,
    "jenis": fields.String(enum=service.JENIS, example="SAKIT"),
    "tanggal_mulai": fields.Date,
    "tanggal_selesai": fields.Date,
    "jumlah_hari": fields.Integer(example=2, description="Hari kalender"),
    "alasan": fields.String,
    "lampiran_url": fields.String(description="GET dengan header Authorization"),
    "status_izin": fields.String(enum=service.STATUS),
    "catatan_proses": fields.String,
    "diproses_oleh": fields.String,
    "diproses_at": fields.DateTime,
    "created_at": fields.DateTime,
})

setujui_out = ns.clone("IzinDisetujui", izin_out, {
    "absensi_dibuat": fields.List(fields.Date, description="Hari kerja yang tercatat di absensi"),
    "absensi_dilewati": fields.List(fields.Date, description="Hari kerja yang sudah punya absensi"),
})

catatan_model = ns.model("IzinCatatan", {"catatan": fields.String(example="Lampiran sudah dicek")})
tolak_model = ns.model("IzinTolak", {"catatan": fields.String(required=True, example="Lampiran tidak jelas")})


# ---------- pegawai ----------

@ns.route("")
class IzinList(Resource):
    @roles_required()
    @ns.expect(ajukan_parser)
    @ns.response(201, "Izin diajukan", docs.envelope(ns, izin_out))
    def post(self):
        """(pegawai) Ajukan izin / sakit / cuti / dinas

        multipart/form-data. Status awal PENDING. Dicatat di audit log.
        Error: `FIELD_WAJIB_KOSONG`, `PARAMETER_TIDAK_VALID`, `LAMPIRAN_WAJIB`, `RENTANG_IZIN_TERLALU_PANJANG`,
        `FORMAT_FILE_TIDAK_DIDUKUNG` (400), `BUKAN_PEGAWAI` (403), `IZIN_BENTROK` (409).
        """
        return {"data": service.ajukan(current_pegawai_id(), request.form, request.files.get("lampiran"),
                                       current_user_id())}, 201

    @roles_required(*MONITOR)
    @ns.expect(list_parser)
    @ns.response(200, "OK", docs.paginated(ns, izin_out))
    def get(self):
        """(admin) Daftar pengajuan izin (filter + paginasi)

        Role: ADMIN, OPERATOR, KADES. PENDING tampil paling atas, lalu terbaru.
        """
        return {"data": service.list_izin(request.args)}


@ns.route("/saya")
class IzinSaya(Resource):
    @roles_required()
    @ns.expect(saya_parser)
    @ns.response(200, "OK", docs.paginated(ns, izin_out))
    def get(self):
        """(pegawai) Riwayat pengajuan izin saya"""
        return {"data": service.list_izin_saya(current_pegawai_id(), request.args)}


# ---------- pegawai & admin ----------

@ns.route("/<int:id_izin>")
class IzinDetail(Resource):
    @roles_required()
    @ns.response(200, "OK", docs.envelope(ns, izin_out))
    def get(self, id_izin):
        """(pegawai & admin) Detail izin

        Panel admin (ADMIN, OPERATOR, KADES): semua. Pegawai: hanya miliknya.
        Error: `IZIN_TIDAK_DITEMUKAN` (404).
        """
        return {"data": service.detail_izin(id_izin, _pemilik())}


@ns.route("/<int:id_izin>/lampiran")
class IzinLampiran(Resource):
    @roles_required()
    @ns.produces(["image/jpeg", "image/png", "application/pdf"])
    @ns.response(200, "File lampiran")
    def get(self, id_izin):
        """(pegawai & admin) Unduh lampiran izin

        Panel admin: semua. Pegawai: hanya miliknya.
        Error: `IZIN_TIDAK_DITEMUKAN`, `FILE_TIDAK_DITEMUKAN` (404).
        """
        return send_file(service.path_lampiran(id_izin, _pemilik()), max_age=86400)


@ns.route("/<int:id_izin>/batal")
class IzinBatal(Resource):
    @roles_required()
    @ns.expect(catatan_model)
    @ns.response(200, "Izin dibatalkan", docs.envelope(ns, izin_out))
    def post(self, id_izin):
        """(pegawai & admin) Batalkan izin

        Pegawai: izin miliknya yang masih PENDING. Panel admin (ADMIN, KADES): PENDING atau DISETUJUI;
        baris absensi dari izin yang disetujui ikut dihapus. Dicatat di audit log.
        Error: `AKSES_DITOLAK` (403), `IZIN_TIDAK_DITEMUKAN` (404), `STATUS_IZIN_TIDAK_VALID` (409).
        """
        if _admin():
            if current_role() not in PEMROSES:
                raise AppError("AKSES_DITOLAK", "Anda tidak memiliki akses ke fitur ini", 403)
            pemilik = None
        else:
            pemilik = current_pegawai_id()
        return {"data": service.batalkan(id_izin, request.get_json(silent=True), current_user_id(), pemilik)}


# ---------- proses (admin) ----------

@ns.route("/<int:id_izin>/setujui")
class IzinSetujui(Resource):
    @roles_required(*PEMROSES)
    @ns.expect(catatan_model)
    @ns.response(200, "Izin disetujui", docs.envelope(ns, setujui_out))
    def post(self, id_izin):
        """(admin) Setujui izin

        Role: ADMIN, KADES. Hanya izin PENDING. Membuat baris absensi (status = jenis izin) untuk
        setiap hari kerja di rentang izin; hari yang sudah punya absensi dilewati. Dicatat di audit log.
        Error: `IZIN_TIDAK_DITEMUKAN` (404), `STATUS_IZIN_TIDAK_VALID` (409).
        """
        return {"data": service.setujui(id_izin, request.get_json(silent=True), current_user_id())}


@ns.route("/<int:id_izin>/tolak")
class IzinTolak(Resource):
    @roles_required(*PEMROSES)
    @ns.expect(tolak_model)
    @ns.response(200, "Izin ditolak", docs.envelope(ns, izin_out))
    def post(self, id_izin):
        """(admin) Tolak izin

        Role: ADMIN, KADES. Hanya izin PENDING, `catatan` (alasan penolakan) wajib. Dicatat di audit log.
        Error: `FIELD_WAJIB_KOSONG` (400), `IZIN_TIDAK_DITEMUKAN` (404), `STATUS_IZIN_TIDAK_VALID` (409).
        """
        return {"data": service.tolak(id_izin, request.get_json(silent=True), current_user_id())}
