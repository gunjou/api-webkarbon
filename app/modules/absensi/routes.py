"""
Endpoint absensi.

Pegawai (semua role yang akunnya tertaut ke data pegawai):
  POST /masuk, /pulang, GET /saya/hari-ini, GET /saya, GET /{id} & foto milik sendiri
Admin / monitoring:
  ADMIN, OPERATOR, KADES -> baca (list, harian, rekap, detail, percobaan, foto)
  ADMIN                  -> input manual, koreksi, hapus, kelola hari libur

Parser di bawah (ns.parser) dipakai untuk dokumentasi Swagger. Validasi & konversi tipe
dilakukan di service lewat app.core.params, supaya format error tetap {"error": {...}}.
"""
from flask import request, send_file
from flask_restx import Namespace, Resource, fields
from werkzeug.datastructures import FileStorage

from app.core import docs
from app.core.auth import (ADMIN, KADES, OPERATOR, current_pegawai_id, current_role, current_user_id,
                           roles_required)

from . import service

ns = Namespace("Absensi", description=(
    "Absen masuk/pulang, monitor, manajemen absensi, rekap, hari libur. "
    "Label: (pegawai) = akun yang tertaut pegawai, untuk aplikasi absen; "
    "(admin) = ADMIN/OPERATOR/KADES, untuk panel admin; "
    "(pegawai & admin) = dipakai keduanya, pegawai hanya melihat data miliknya."))

MONITOR = (ADMIN, OPERATOR, KADES)
STATUS = ["HADIR", "IZIN", "SAKIT", "CUTI", "DINAS"]


def _pemilik():
    """Role monitor boleh melihat semua; role lain hanya absensi miliknya sendiri."""
    return None if current_role() in MONITOR else current_pegawai_id()


# ---------- parser (Swagger) ----------

absen_parser = ns.parser()
absen_parser.add_argument("foto", location="files", type=FileStorage, required=True,
                          help="Foto selfie dari kamera (JPG/PNG), satu wajah")
absen_parser.add_argument("latitude", location="form", type=float, required=True, help="Dari GPS HP, mis. -8.62")
absen_parser.add_argument("longitude", location="form", type=float, required=True, help="Dari GPS HP, mis. 116.1")
absen_parser.add_argument("akurasi", location="form", type=float, required=True,
                          help="Akurasi GPS dalam meter (position.coords.accuracy)")

bulan_parser = ns.parser()
bulan_parser.add_argument("bulan", location="args", type=int, help="1-12, default bulan ini")
bulan_parser.add_argument("tahun", location="args", type=int, help="Default tahun ini")

rekap_parser = bulan_parser.copy()
rekap_parser.add_argument("id_pegawai", location="args", type=int, help="Kosongkan untuk semua pegawai")

list_parser = ns.parser()
list_parser.add_argument("tanggal_mulai", location="args", help="YYYY-MM-DD")
list_parser.add_argument("tanggal_selesai", location="args", help="YYYY-MM-DD")
list_parser.add_argument("id_pegawai", location="args", type=int)
list_parser.add_argument("status", location="args", choices=STATUS)
list_parser.add_argument("page", location="args", type=int, default=1)
list_parser.add_argument("per_page", location="args", type=int, default=20, help="Maks 100")

percobaan_parser = ns.parser()
percobaan_parser.add_argument("tanggal_mulai", location="args", help="YYYY-MM-DD")
percobaan_parser.add_argument("tanggal_selesai", location="args", help="YYYY-MM-DD")
percobaan_parser.add_argument("id_pegawai", location="args", type=int)
percobaan_parser.add_argument("page", location="args", type=int, default=1)
percobaan_parser.add_argument("per_page", location="args", type=int, default=20, help="Maks 100")

harian_parser = ns.parser()
harian_parser.add_argument("tanggal", location="args", help="YYYY-MM-DD, default hari ini")

tahun_parser = ns.parser()
tahun_parser.add_argument("tahun", location="args", type=int, help="Default tahun ini")


# ---------- model ----------

absensi_out = ns.model("Absensi", {
    "id_absensi": fields.Integer(example=1),
    "id_pegawai": fields.Integer(example=2),
    "nama_pegawai": fields.String(example="Kaharudin"),
    "jabatan": fields.String(example="Sekretaris Desa"),
    "tanggal": fields.Date,
    "status_kehadiran": fields.String(enum=STATUS),
    "id_izin": fields.Integer,
    "jadwal_masuk": fields.String(example="08:00:00", description="Snapshot jadwal hari itu"),
    "jadwal_pulang": fields.String(example="14:00:00"),
    "toleransi_menit": fields.Integer(example=15),
    "jam_masuk": fields.DateTime, "lat_masuk": fields.Float, "lng_masuk": fields.Float,
    "akurasi_masuk": fields.Float, "id_lokasi_masuk": fields.Integer, "nama_lokasi_masuk": fields.String,
    "skor_masuk": fields.Float(description="Jarak wajah, makin kecil makin mirip"),
    "foto_masuk": fields.String, "foto_masuk_url": fields.String(example="/api/absensi/1/foto/masuk"),
    "jam_pulang": fields.DateTime, "lat_pulang": fields.Float, "lng_pulang": fields.Float,
    "akurasi_pulang": fields.Float, "id_lokasi_pulang": fields.Integer, "nama_lokasi_pulang": fields.String,
    "skor_pulang": fields.Float,
    "foto_pulang": fields.String, "foto_pulang_url": fields.String(example="/api/absensi/1/foto/pulang"),
    "menit_telat": fields.Integer(example=0),
    "menit_pulang_cepat": fields.Integer(example=0),
    "keterangan": fields.String,
    "is_koreksi": fields.Boolean(description="true kalau diinput manual / dikoreksi admin"),
    "created_by": fields.Integer, "created_at": fields.DateTime,
    "updated_by": fields.Integer, "updated_at": fields.DateTime,
})

libur_out = ns.model("HariLibur", {
    "tanggal": fields.Date(example="2026-12-25"),
    "keterangan": fields.String(example="Hari Raya Natal"),
    "created_at": fields.DateTime,
})

jadwal_out = ns.model("JadwalHariIni", {
    "jam_masuk": fields.String(example="08:00:00"),
    "jam_pulang": fields.String(example="14:00:00"),
    "toleransi_menit": fields.Integer(example=15),
})

hari_ini_out = ns.model("StatusAbsenHariIni", {
    "tanggal": fields.Date,
    "hari_kerja": fields.Boolean,
    "libur": fields.Nested(libur_out, allow_null=True),
    "jadwal": fields.Nested(jadwal_out),
    "wajah_terdaftar": fields.Boolean(description="false -> belum bisa absen, hubungi admin"),
    "absensi": fields.Nested(absensi_out, allow_null=True),
    "bisa_masuk": fields.Boolean,
    "bisa_pulang": fields.Boolean,
})

rekap_item = ns.model("RekapPegawai", {
    "id_pegawai": fields.Integer, "nama": fields.String, "jabatan": fields.String,
    "hari_kerja": fields.Integer(description="Hari kerja sebulan (tanpa libur, sejak tanggal_mulai pegawai)"),
    "hadir": fields.Integer, "telat_kali": fields.Integer, "telat_menit": fields.Integer,
    "pulang_cepat_kali": fields.Integer, "pulang_cepat_menit": fields.Integer,
    "tidak_absen_pulang": fields.Integer,
    "izin": fields.Integer, "sakit": fields.Integer, "cuti": fields.Integer, "dinas": fields.Integer,
    "alpha": fields.Integer(description="Hari kerja yang sudah lewat tanpa data absensi"),
})

riwayat_out = ns.model("RiwayatAbsensi", {
    "bulan": fields.Integer, "tahun": fields.Integer,
    "rekap": fields.Nested(rekap_item),
    "items": fields.List(fields.Nested(absensi_out)),
})

rekap_out = ns.model("RekapBulanan", {
    "bulan": fields.Integer, "tahun": fields.Integer,
    "items": fields.List(fields.Nested(rekap_item)),
})

harian_item = ns.model("MonitorHarianItem", {
    "id_pegawai": fields.Integer, "nama": fields.String, "jabatan": fields.String,
    "foto_wajah_url": fields.String,
    "status": fields.String(enum=STATUS + ["ALPHA", "BELUM_ABSEN", "LIBUR"]),
    "absensi": fields.Nested(absensi_out, allow_null=True),
})

harian_out = ns.model("MonitorHarian", {
    "tanggal": fields.Date,
    "hari_kerja": fields.Boolean,
    "libur": fields.Nested(libur_out, allow_null=True),
    "ringkasan": fields.Raw(example={"HADIR": 5, "BELUM_ABSEN": 2, "IZIN": 1}),
    "items": fields.List(fields.Nested(harian_item)),
})

manual_model = ns.model("AbsensiManual", {
    "id_pegawai": fields.Integer(required=True, example=2),
    "tanggal": fields.Date(required=True, example="2026-10-28"),
    "status_kehadiran": fields.String(enum=STATUS, default="HADIR"),
    "jam_masuk": fields.String(example="08:05", description="HH:MM, wajib kalau HADIR"),
    "jam_pulang": fields.String(example="14:00", description="HH:MM, opsional"),
    "keterangan": fields.String(required=True, example="HP rusak, absen dicatat manual"),
})

koreksi_model = ns.model("AbsensiKoreksi", {
    "status_kehadiran": fields.String(enum=STATUS, default="HADIR"),
    "jam_masuk": fields.String(example="08:05", description="HH:MM, wajib kalau HADIR"),
    "jam_pulang": fields.String(example="14:00", description="HH:MM, opsional"),
    "keterangan": fields.String(required=True, example="Lupa absen pulang, dikonfirmasi atasan"),
})

percobaan_out = ns.model("PercobaanAbsen", {
    "id_percobaan": fields.Integer, "id_pegawai": fields.Integer, "nama_pegawai": fields.String,
    "tipe": fields.String(enum=["MASUK", "PULANG"]),
    "alasan_gagal": fields.String(example="DI_LUAR_RADIUS"),
    "latitude": fields.Float, "longitude": fields.Float, "akurasi": fields.Float,
    "jarak_meter": fields.Float, "skor_wajah": fields.Float,
    "foto_path": fields.String, "foto_url": fields.String, "created_at": fields.DateTime,
})

libur_input = ns.model("HariLiburInput", {
    "tanggal": fields.Date(required=True, example="2026-12-25"),
    "keterangan": fields.String(required=True, example="Hari Raya Natal"),
})

libur_ubah = ns.model("HariLiburUbah", {
    "keterangan": fields.String(required=True, example="Hari Raya Natal"),
})



# ---------- pegawai ----------

@ns.route("/masuk")
class AbsenMasuk(Resource):
    @roles_required()
    @ns.expect(absen_parser)
    @ns.response(201, "Absen masuk tercatat", docs.envelope(ns, absensi_out))
    def post(self):
        """(pegawai) Absen masuk

        Semua role yang akunnya tertaut ke pegawai. multipart/form-data: `foto`, `latitude`, `longitude`,
        `akurasi`. Jam diambil dari server (WITA). Percobaan yang gagal dicatat untuk admin.
        Error: `FIELD_WAJIB_KOSONG`, `PARAMETER_TIDAK_VALID`, `FILE_KOSONG`, `WAJAH_BELUM_TERDAFTAR`,
        `LOKASI_BELUM_DIATUR`, `BUKAN_HARI_KERJA`, `AKURASI_GPS_RENDAH`, `DI_LUAR_RADIUS`, `FOTO_TIDAK_VALID`,
        `WAJAH_TIDAK_TERDETEKSI`, `WAJAH_LEBIH_DARI_SATU`, `WAJAH_TIDAK_COCOK` (400), `BUKAN_PEGAWAI` (403),
        `SUDAH_ADA_KETERANGAN`, `SUDAH_ABSEN_MASUK` (409).
        """
        return {"data": service.absen(service.MASUK, current_pegawai_id(), request.files.get("foto"),
                                      request.form, current_user_id())}, 201


@ns.route("/pulang")
class AbsenPulang(Resource):
    @roles_required()
    @ns.expect(absen_parser)
    @ns.response(200, "Absen pulang tercatat", docs.envelope(ns, absensi_out))
    def post(self):
        """(pegawai) Absen pulang

        Sama seperti absen masuk. Harus sudah absen masuk hari ini.
        Error: `FIELD_WAJIB_KOSONG`, `PARAMETER_TIDAK_VALID`, `FILE_KOSONG`, `WAJAH_BELUM_TERDAFTAR`,
        `LOKASI_BELUM_DIATUR`, `BUKAN_HARI_KERJA`, `AKURASI_GPS_RENDAH`, `DI_LUAR_RADIUS`, `FOTO_TIDAK_VALID`,
        `WAJAH_TIDAK_TERDETEKSI`, `WAJAH_LEBIH_DARI_SATU`, `WAJAH_TIDAK_COCOK`, `BELUM_ABSEN_MASUK` (400), `BUKAN_PEGAWAI` (403),
        `SUDAH_ADA_KETERANGAN`, `SUDAH_ABSEN_PULANG` (409).
        """
        return {"data": service.absen(service.PULANG, current_pegawai_id(), request.files.get("foto"),
                                      request.form, current_user_id())}


@ns.route("/saya/hari-ini")
class AbsenSayaHariIni(Resource):
    @roles_required()
    @ns.response(200, "OK", docs.envelope(ns, hari_ini_out))
    def get(self):
        """(pegawai) Status absen saya hari ini

        Untuk layar absen: jadwal, libur, data absen hari ini, `bisa_masuk` / `bisa_pulang`.
        Error: `BUKAN_PEGAWAI` (403).
        """
        return {"data": service.status_hari_ini(current_pegawai_id())}


@ns.route("/saya")
class AbsenSaya(Resource):
    @roles_required()
    @ns.expect(bulan_parser)
    @ns.response(200, "OK", docs.envelope(ns, riwayat_out))
    def get(self):
        """(pegawai) Riwayat & rekap absensi saya per bulan

        Error: `PARAMETER_TIDAK_VALID` (400), `BUKAN_PEGAWAI` (403).
        """
        return {"data": service.riwayat_saya(current_pegawai_id(), request.args)}


# ---------- monitor & manajemen (admin) ----------

@ns.route("")
class AbsensiList(Resource):
    @roles_required(*MONITOR)
    @ns.expect(list_parser)
    @ns.response(200, "OK", docs.paginated(ns, absensi_out))
    def get(self):
        """(admin) Daftar absensi (filter + paginasi)

        Role: ADMIN, OPERATOR, KADES. Urut tanggal terbaru.
        """
        return {"data": service.list_absensi(request.args)}

    @roles_required(ADMIN)
    @ns.expect(manual_model)
    @ns.response(201, "Absensi ditambahkan", docs.envelope(ns, absensi_out))
    def post(self):
        """(admin) Input absensi manual

        Role: ADMIN. Untuk pegawai yang tidak bisa absen lewat HP, atau mencatat IZIN/SAKIT/CUTI/DINAS.
        `keterangan` (alasan) wajib. Menit telat dihitung otomatis dari jadwal. Dicatat di audit log.
        Error: `FIELD_WAJIB_KOSONG`, `PARAMETER_TIDAK_VALID`, `TANGGAL_TIDAK_VALID` (400),
        `PEGAWAI_TIDAK_DITEMUKAN` (404), `ABSENSI_SUDAH_ADA` (409, details.id_absensi).
        """
        return {"data": service.input_manual(request.get_json(silent=True), current_user_id())}, 201


@ns.route("/harian")
class AbsensiHarian(Resource):
    @roles_required(*MONITOR)
    @ns.expect(harian_parser)
    @ns.response(200, "OK", docs.envelope(ns, harian_out))
    def get(self):
        """(admin) Monitor harian

        Role: ADMIN, OPERATOR, KADES. Semua pegawai aktif + status pada tanggal itu:
        HADIR / IZIN / SAKIT / CUTI / DINAS / BELUM_ABSEN (hari ini) / ALPHA (sudah lewat) / LIBUR.
        """
        return {"data": service.monitor_harian(request.args)}


@ns.route("/rekap")
class AbsensiRekap(Resource):
    @roles_required(*MONITOR)
    @ns.expect(rekap_parser)
    @ns.response(200, "OK", docs.envelope(ns, rekap_out))
    def get(self):
        """(admin) Rekap bulanan per pegawai

        Role: ADMIN, OPERATOR, KADES. Dipakai juga untuk payroll nanti.
        """
        return {"data": service.rekap_bulanan(request.args)}


@ns.route("/<int:id_absensi>")
@ns.param("id_absensi", "ID absensi")
class AbsensiItem(Resource):
    @roles_required()
    @ns.response(200, "OK", docs.envelope(ns, absensi_out))
    def get(self, id_absensi):
        """(pegawai & admin) Detail absensi

        ADMIN, OPERATOR, KADES: semua. Role lain: hanya absensi miliknya.
        Error: `ABSENSI_TIDAK_DITEMUKAN` (404).
        """
        return {"data": service.detail_absensi(id_absensi, _pemilik())}

    @roles_required(ADMIN)
    @ns.expect(koreksi_model)
    @ns.response(200, "Absensi dikoreksi", docs.envelope(ns, absensi_out))
    def put(self, id_absensi):
        """(admin) Koreksi absensi

        Role: ADMIN. Semua field dikirim ulang; `keterangan` (alasan koreksi) wajib.
        Menit telat / pulang cepat dihitung ulang dari jadwal hari itu. Dicatat di audit log.
        Error: `FIELD_WAJIB_KOSONG`, `PARAMETER_TIDAK_VALID`, `TANGGAL_TIDAK_VALID` (400),
        `ABSENSI_TIDAK_DITEMUKAN` (404).
        """
        return {"data": service.koreksi_absensi(id_absensi, request.get_json(silent=True), current_user_id())}

    @roles_required(ADMIN)
    @ns.response(200, "Absensi dihapus", docs.message(ns))
    def delete(self, id_absensi):
        """(admin) Hapus absensi

        Role: ADMIN. Data lama tersimpan di audit log. Error: `ABSENSI_TIDAK_DITEMUKAN` (404).
        """
        service.hapus_absensi(id_absensi, current_user_id())
        return {"data": {"message": "Absensi dihapus"}}


@ns.route("/<int:id_absensi>/foto/<string:tipe>")
@ns.param("id_absensi", "ID absensi")
@ns.param("tipe", "masuk / pulang", enum=["masuk", "pulang"])
class AbsensiFoto(Resource):
    @roles_required()
    @ns.produces(["image/jpeg"])
    @ns.response(200, "File JPEG")
    def get(self, id_absensi, tipe):
        """(pegawai & admin) Foto absen masuk / pulang (image/jpeg)

        ADMIN, OPERATOR, KADES: semua. Role lain: hanya miliknya.
        Error: `ABSENSI_TIDAK_DITEMUKAN`, `FILE_TIDAK_DITEMUKAN` (404).
        """
        return send_file(service.path_foto_absensi(id_absensi, tipe, _pemilik()),
                         mimetype="image/jpeg", max_age=86400)


@ns.route("/percobaan")
class PercobaanList(Resource):
    @roles_required(*MONITOR)
    @ns.expect(percobaan_parser)
    @ns.response(200, "OK", docs.paginated(ns, percobaan_out))
    def get(self):
        """(admin) Log percobaan absen yang gagal

        Role: ADMIN, OPERATOR, KADES. Untuk menangani komplain & mendeteksi kecurangan
        (di luar radius, wajah tidak cocok, dst).
        """
        return {"data": service.list_percobaan(request.args)}


@ns.route("/percobaan/<int:id_percobaan>/foto")
@ns.param("id_percobaan", "ID percobaan")
class PercobaanFoto(Resource):
    @roles_required(*MONITOR)
    @ns.produces(["image/jpeg"])
    @ns.response(200, "File JPEG")
    def get(self, id_percobaan):
        """(admin) Foto percobaan absen gagal (hanya ada untuk WAJAH_TIDAK_COCOK)

        Role: ADMIN, OPERATOR, KADES. Error: `FILE_TIDAK_DITEMUKAN` (404).
        """
        return send_file(service.path_foto_percobaan(id_percobaan), mimetype="image/jpeg", max_age=86400)


# ---------- hari libur ----------

@ns.route("/hari-libur")
class HariLiburList(Resource):
    @roles_required()
    @ns.expect(tahun_parser)
    @ns.response(200, "OK", docs.envelope_list(ns, libur_out))
    def get(self):
        """(pegawai & admin) Daftar hari libur per tahun

        Semua role (pegawai juga perlu tahu).
        """
        return {"data": service.list_hari_libur(request.args)}

    @roles_required(ADMIN)
    @ns.expect(libur_input)
    @ns.response(201, "Hari libur ditambahkan", docs.envelope(ns, libur_out))
    def post(self):
        """(admin) Tambah hari libur

        Role: ADMIN. Error: `FIELD_WAJIB_KOSONG`, `PARAMETER_TIDAK_VALID` (400), `HARI_LIBUR_SUDAH_ADA` (409).
        """
        return {"data": service.tambah_hari_libur(request.get_json(silent=True), current_user_id())}, 201


@ns.route("/hari-libur/<string:tanggal>")
@ns.param("tanggal", "YYYY-MM-DD")
class HariLiburItem(Resource):
    @roles_required(ADMIN)
    @ns.expect(libur_ubah)
    @ns.response(200, "Hari libur diubah", docs.envelope(ns, libur_out))
    def put(self, tanggal):
        """(admin) Ubah keterangan hari libur

        Role: ADMIN. Error: `HARI_LIBUR_TIDAK_DITEMUKAN` (404).
        """
        return {"data": service.ubah_hari_libur(tanggal, request.get_json(silent=True), current_user_id())}

    @roles_required(ADMIN)
    @ns.response(200, "Hari libur dihapus", docs.message(ns))
    def delete(self, tanggal):
        """(admin) Hapus hari libur

        Role: ADMIN. Error: `HARI_LIBUR_TIDAK_DITEMUKAN` (404).
        """
        service.hapus_hari_libur(tanggal, current_user_id())
        return {"data": {"message": "Hari libur dihapus"}}
