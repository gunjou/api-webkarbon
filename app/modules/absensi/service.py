"""
Absensi: absen masuk/pulang (pegawai), monitor & manajemen (admin), rekap, hari libur.

Bergantung pada modul lain (lewat service, bukan query langsung):
  lokasi_absen.service.list_lokasi_aktif(conn)       -> geofence (geo.py)
  kepegawaian.service.get_embedding_wajah(conn, id)  -> verifikasi wajah (app.core.face)
  kepegawaian.service.list_pegawai_aktif(conn)       -> monitor harian & rekap
  pengaturan 'jadwal_kerja' & 'absensi'              -> jam kerja, toleransi, akurasi GPS, threshold wajah

absen(tipe, ...) — urutan validasi (murah dulu, face recognition terakhir):
  1. pegawai aktif & sudah punya wajah    2. hari kerja / bukan hari libur
  3. belum absen (tipe ini) hari ini      4. akurasi GPS <= batas
  5. di dalam radius lokasi terdekat      6. wajah cocok
  gagal di 2, 4, 5, 6 -> dicatat ke percobaan_absen (transaksi terpisah, tetap tersimpan walau request gagal)
  waktu SELALU now_wita() dari server, bukan dari HP

Satu baris absensi = satu pegawai satu hari. Hari kerja tanpa baris = ALPHA (dihitung saat
monitor/rekap, tanpa cron). Menit telat dihitung dari jadwal masuk, hanya kalau lewat toleransi.

Dipakai modul perizinan (lewat service):
  buat_absensi_izin(conn, izin, user_id) -> izin DISETUJUI: satu baris absensi per hari kerja (id_izin terisi)
  hapus_absensi_izin(conn, id_izin)      -> izin dibatalkan setelah disetujui
"""
import calendar
from datetime import date, datetime, timedelta

from app.core import face, params, storage
from app.core.audit import catat_audit
from app.core.db import WITA, get_connection, now_wita, today_wita
from app.core.errors import AppError, require_fields
from app.modules.kepegawaian import service as kepegawaian
from app.modules.lokasi_absen import service as lokasi_absen
from app.modules.pengaturan.queries import get_pengaturan

from . import geo
from . import queries as q

MASUK, PULANG = "MASUK", "PULANG"
HADIR = "HADIR"
STATUS_KEHADIRAN = ["HADIR", "IZIN", "SAKIT", "CUTI", "DINAS"]

PESAN_FOTO = {
    "FOTO_TIDAK_VALID": "File bukan gambar yang valid (gunakan JPG/PNG)",
    "WAJAH_TIDAK_TERDETEKSI": "Wajah tidak terdeteksi. Pastikan wajah terlihat jelas & pencahayaan cukup",
    "WAJAH_LEBIH_DARI_SATU": "Terdeteksi lebih dari satu wajah. Pastikan hanya Anda di foto",
}


# ---------- pengaturan ----------

def _jadwal(conn):
    j = get_pengaturan(conn, "jadwal_kerja", {}) or {}
    return {
        "hari_kerja": [int(h) for h in j.get("hari_kerja", [1, 2, 3, 4, 5])],  # 1 = Senin ... 7 = Minggu
        "jam_masuk": params.jam(j.get("jam_masuk") or "08:00", "jadwal_kerja.jam_masuk"),
        "jam_pulang": params.jam(j.get("jam_pulang") or "14:00", "jadwal_kerja.jam_pulang"),
        "toleransi_menit": int(j.get("toleransi_menit", 15)),
    }


def _setelan_absensi(conn):
    s = get_pengaturan(conn, "absensi", {}) or {}
    return {"max_akurasi_meter": float(s.get("max_akurasi_meter", 50)),
            "face_threshold": float(s.get("face_threshold", 0.5))}


def _cek_hari(conn, tanggal, jadwal):
    """Return (hari_kerja: bool, libur: dict|None)."""
    libur = q.get_hari_libur(conn, tanggal)
    return tanggal.isoweekday() in jadwal["hari_kerja"] and libur is None, libur


# ---------- hitung menit ----------

def _waktu(tanggal, jam):
    return datetime.combine(tanggal, jam, tzinfo=WITA) if jam else None


def _menit_telat(jam_masuk, tanggal, jadwal_masuk, toleransi):
    """Dihitung dari jadwal masuk, hanya kalau lewat toleransi. 08:20 (jadwal 08:00, toleransi 15) = 20."""
    if not jam_masuk or not jadwal_masuk:
        return 0
    batas = _waktu(tanggal, jadwal_masuk)
    if jam_masuk <= batas + timedelta(minutes=toleransi or 0):
        return 0
    return int((jam_masuk - batas).total_seconds() // 60)


def _menit_pulang_cepat(jam_pulang, tanggal, jadwal_pulang):
    if not jam_pulang or not jadwal_pulang:
        return 0
    batas = _waktu(tanggal, jadwal_pulang)
    return int((batas - jam_pulang).total_seconds() // 60) if jam_pulang < batas else 0


# ---------- output ----------

def _out(absensi):
    """Tambah URL foto (GET dengan header Authorization)."""
    if not absensi:
        return None
    i = absensi["id_absensi"]
    return {**absensi,
            "foto_masuk_url": f"/api/absensi/{i}/foto/masuk" if absensi["foto_masuk"] else None,
            "foto_pulang_url": f"/api/absensi/{i}/foto/pulang" if absensi["foto_pulang"] else None}


def _get_absensi(conn, id_absensi, id_pegawai_pemilik=None):
    """id_pegawai_pemilik diisi untuk role PEGAWAI: hanya boleh melihat absensi sendiri."""
    absensi = q.get_absensi(conn, id_absensi)
    if not absensi or (id_pegawai_pemilik and absensi["id_pegawai"] != id_pegawai_pemilik):
        raise AppError("ABSENSI_TIDAK_DITEMUKAN", "Data absensi tidak ditemukan", 404)
    return absensi


# ---------- absen masuk / pulang (pegawai) ----------

def _gagal(ctx, alasan, pesan, status=400, foto=None, details=None):
    """Catat percobaan gagal di transaksi terpisah (tetap tersimpan), lalu raise."""
    with get_connection().begin() as conn:
        q.insert_percobaan(conn, {
            **ctx, "alasan_gagal": alasan, "now": now_wita(),
            "foto_path": storage.save_bytes(foto, "percobaan_absen", "jpg") if foto else None,
        })
    raise AppError(alasan, pesan, status, details)


def absen(tipe, id_pegawai, file, form, user_id):
    lat = params.angka(form.get("latitude"), "latitude", wajib=True, minimal=-90, maksimal=90)
    lng = params.angka(form.get("longitude"), "longitude", wajib=True, minimal=-180, maksimal=180)
    akurasi = params.angka(form.get("akurasi"), "akurasi", wajib=True, minimal=0)
    if not file or not file.filename:
        raise AppError("FILE_KOSONG", "Foto belum diambil (field multipart: foto)", 400)

    now = now_wita()
    tanggal = now.date()
    ctx = {"id_pegawai": id_pegawai, "tipe": tipe, "lat": lat, "lng": lng, "akurasi": akurasi,
           "jarak_meter": None, "skor_wajah": None}

    with get_connection().connect() as conn:
        kepegawaian.get_pegawai(conn, id_pegawai)
        embedding = kepegawaian.get_embedding_wajah(conn, id_pegawai)
        jadwal, setelan = _jadwal(conn), _setelan_absensi(conn)
        hari_kerja, libur = _cek_hari(conn, tanggal, jadwal)
        hari_ini = q.get_absensi_harian(conn, id_pegawai, tanggal)
        daftar_lokasi = lokasi_absen.list_lokasi_aktif(conn)

    # 1. sudah punya wajah
    if embedding is None:
        raise AppError("WAJAH_BELUM_TERDAFTAR", "Wajah Anda belum didaftarkan. Hubungi admin", 400)

    # 2. hari kerja
    if not hari_kerja:
        _gagal(ctx, "BUKAN_HARI_KERJA",
               f"Hari ini libur: {libur['keterangan']}" if libur else "Hari ini bukan hari kerja")

    # 3. status absen hari ini
    if hari_ini and hari_ini["status_kehadiran"] != HADIR:
        raise AppError("SUDAH_ADA_KETERANGAN",
                       f"Hari ini Anda tercatat {hari_ini['status_kehadiran']}", 409)
    if tipe == MASUK and hari_ini:
        raise AppError("SUDAH_ABSEN_MASUK", "Anda sudah absen masuk hari ini", 409)
    if tipe == PULANG:
        if not hari_ini or not hari_ini["jam_masuk"]:
            raise AppError("BELUM_ABSEN_MASUK", "Anda belum absen masuk hari ini", 400)
        if hari_ini["jam_pulang"]:
            raise AppError("SUDAH_ABSEN_PULANG", "Anda sudah absen pulang hari ini", 409)

    # 4. akurasi GPS
    if akurasi > setelan["max_akurasi_meter"]:
        _gagal(ctx, "AKURASI_GPS_RENDAH",
               f"Akurasi GPS {akurasi:.0f} m, maksimal {setelan['max_akurasi_meter']:.0f} m. "
               "Aktifkan GPS mode akurasi tinggi lalu coba lagi",
               details={"akurasi": akurasi, "max_akurasi_meter": setelan["max_akurasi_meter"]})

    # 5. radius lokasi
    if not daftar_lokasi:
        raise AppError("LOKASI_BELUM_DIATUR", "Lokasi absen belum diatur. Hubungi admin", 400)
    lokasi, jarak, di_dalam = geo.lokasi_terdekat(lat, lng, daftar_lokasi)
    ctx["jarak_meter"] = round(jarak, 1)
    if not di_dalam:
        _gagal(ctx, "DI_LUAR_RADIUS",
               f"Anda berada {jarak:.0f} m dari {lokasi['nama']} (radius {lokasi['radius_meter']} m)",
               details={"jarak_meter": round(jarak, 1), "id_lokasi": lokasi["id_lokasi"],
                        "nama_lokasi": lokasi["nama"], "radius_meter": lokasi["radius_meter"]})

    # 6. wajah
    try:
        cocok, skor, jpeg = face.proses_absen(file.read(), embedding, setelan["face_threshold"])
    except ValueError as e:
        kode = str(e)
        _gagal(ctx, kode, PESAN_FOTO.get(kode, kode))
    ctx["skor_wajah"] = round(skor, 4)
    if not cocok:
        _gagal(ctx, "WAJAH_TIDAK_COCOK", "Wajah tidak cocok dengan data pegawai", foto=jpeg,
               details={"skor_wajah": round(skor, 4), "threshold": setelan["face_threshold"]})

    # simpan
    data = {"id_pegawai": id_pegawai, "tanggal": tanggal, "jam": now, "lat": lat, "lng": lng,
            "akurasi": akurasi, "id_lokasi": lokasi["id_lokasi"], "skor": round(skor, 4),
            "foto": storage.save_bytes(jpeg, "absensi", "jpg"), "user": user_id, "now": now}
    with get_connection().begin() as conn:
        if tipe == MASUK:
            id_absensi = q.insert_masuk(conn, {
                **data, "jadwal_masuk": jadwal["jam_masuk"], "jadwal_pulang": jadwal["jam_pulang"],
                "toleransi_menit": jadwal["toleransi_menit"],
                "menit_telat": _menit_telat(now, tanggal, jadwal["jam_masuk"], jadwal["toleransi_menit"]),
            })
            if not id_absensi:
                raise AppError("SUDAH_ABSEN_MASUK", "Anda sudah absen masuk hari ini", 409)
        else:
            id_absensi = q.update_pulang(conn, {
                **data, "id_absensi": hari_ini["id_absensi"],
                "menit_pulang_cepat": _menit_pulang_cepat(now, tanggal, hari_ini["jadwal_pulang"]),
            })
            if not id_absensi:
                raise AppError("SUDAH_ABSEN_PULANG", "Anda sudah absen pulang hari ini", 409)
        return _out(q.get_absensi(conn, id_absensi))


def status_hari_ini(id_pegawai):
    """Untuk layar absen di HP: tombol mana yang aktif & info jadwal."""
    tanggal = today_wita()
    with get_connection().connect() as conn:
        pegawai = kepegawaian.get_pegawai(conn, id_pegawai)
        jadwal = _jadwal(conn)
        hari_kerja, libur = _cek_hari(conn, tanggal, jadwal)
        absensi = q.get_absensi_harian(conn, id_pegawai, tanggal)

    hadir = absensi is None or absensi["status_kehadiran"] == HADIR
    return {
        "tanggal": tanggal,
        "hari_kerja": hari_kerja,
        "libur": libur,
        "jadwal": {"jam_masuk": jadwal["jam_masuk"], "jam_pulang": jadwal["jam_pulang"],
                   "toleransi_menit": jadwal["toleransi_menit"]},
        "wajah_terdaftar": pegawai["id_wajah"] is not None,
        "absensi": _out(absensi),
        "bisa_masuk": hari_kerja and absensi is None,
        "bisa_pulang": hari_kerja and hadir and bool(absensi and absensi["jam_masuk"]
                                                     and not absensi["jam_pulang"]),
    }


# ---------- rekap & monitor ----------

def _rentang_bulan(bulan, tahun):
    return date(tahun, bulan, 1), date(tahun, bulan, calendar.monthrange(tahun, bulan)[1])


def _daftar_tanggal(mulai, selesai):
    return [mulai + timedelta(days=i) for i in range((selesai - mulai).days + 1)]


def _rekap(conn, mulai, selesai, id_pegawai=None):
    jadwal = _jadwal(conn)
    hari_ini = today_wita()
    libur = {r["tanggal"] for r in q.list_hari_libur(conn, mulai, selesai)}
    hari_kerja = [d for d in _daftar_tanggal(mulai, selesai)
                  if d.isoweekday() in jadwal["hari_kerja"] and d not in libur]

    if id_pegawai:
        daftar_pegawai = [kepegawaian.get_pegawai(conn, id_pegawai)]
    else:
        daftar_pegawai = kepegawaian.list_pegawai_aktif(conn)
    per_pegawai = {}
    for a in q.list_absensi_periode(conn, id_pegawai, mulai, selesai):
        per_pegawai.setdefault(a["id_pegawai"], []).append(a)

    hasil = []
    for p in daftar_pegawai:
        data = per_pegawai.get(p["id_pegawai"], [])
        ada = {a["tanggal"] for a in data}
        hk = [d for d in hari_kerja if not p["tanggal_mulai"] or d >= p["tanggal_mulai"]]
        hadir = [a for a in data if a["status_kehadiran"] == HADIR]
        jumlah = {s: sum(1 for a in data if a["status_kehadiran"] == s) for s in STATUS_KEHADIRAN}
        hasil.append({
            "id_pegawai": p["id_pegawai"], "nama": p["nama"], "jabatan": p["jabatan"],
            "hari_kerja": len(hk),
            "hadir": jumlah["HADIR"],
            "telat_kali": sum(1 for a in hadir if a["menit_telat"] > 0),
            "telat_menit": sum(a["menit_telat"] for a in hadir),
            "pulang_cepat_kali": sum(1 for a in hadir if a["menit_pulang_cepat"] > 0),
            "pulang_cepat_menit": sum(a["menit_pulang_cepat"] for a in hadir),
            "tidak_absen_pulang": sum(1 for a in hadir if not a["jam_pulang"] and a["tanggal"] < hari_ini),
            "izin": jumlah["IZIN"], "sakit": jumlah["SAKIT"], "cuti": jumlah["CUTI"], "dinas": jumlah["DINAS"],
            # alpha hanya untuk hari yang sudah lewat (hari ini belum dihitung)
            "alpha": sum(1 for d in hk if d < hari_ini and d not in ada),
        })
    return hasil


def riwayat_saya(id_pegawai, args):
    bulan, tahun = params.bulan_tahun(args)
    mulai, selesai = _rentang_bulan(bulan, tahun)
    with get_connection().connect() as conn:
        items = [_out(a) for a in q.list_absensi_periode(conn, id_pegawai, mulai, selesai)]
        rekap = _rekap(conn, mulai, selesai, id_pegawai)[0]
    return {"bulan": bulan, "tahun": tahun, "rekap": rekap, "items": items}


def rekap_bulanan(args):
    """Titik sambung ke modul payroll nanti."""
    bulan, tahun = params.bulan_tahun(args)
    id_pegawai = params.bilangan(args.get("id_pegawai"), "id_pegawai")
    mulai, selesai = _rentang_bulan(bulan, tahun)
    with get_connection().connect() as conn:
        return {"bulan": bulan, "tahun": tahun, "items": _rekap(conn, mulai, selesai, id_pegawai)}


def monitor_harian(args):
    """Semua pegawai aktif + status pada tanggal itu (termasuk yang belum absen / alpha)."""
    tanggal = params.tanggal(args.get("tanggal"), "tanggal") or today_wita()
    hari_ini = today_wita()
    with get_connection().connect() as conn:
        jadwal = _jadwal(conn)
        hari_kerja, libur = _cek_hari(conn, tanggal, jadwal)
        daftar_pegawai = kepegawaian.list_pegawai_aktif(conn)
        absensi = {a["id_pegawai"]: a for a in q.list_absensi_periode(conn, None, tanggal, tanggal)}

    items, ringkasan = [], {}
    for p in daftar_pegawai:
        if p["tanggal_mulai"] and p["tanggal_mulai"] > tanggal:
            continue
        a = absensi.get(p["id_pegawai"])
        if a:
            status = a["status_kehadiran"]
        elif not hari_kerja:
            status = "LIBUR"
        elif tanggal < hari_ini:
            status = "ALPHA"
        else:
            status = "BELUM_ABSEN"
        ringkasan[status] = ringkasan.get(status, 0) + 1
        items.append({"id_pegawai": p["id_pegawai"], "nama": p["nama"], "jabatan": p["jabatan"],
                      "foto_wajah_url": p["foto_wajah_url"], "status": status, "absensi": _out(a)})
    return {"tanggal": tanggal, "hari_kerja": hari_kerja, "libur": libur,
            "ringkasan": ringkasan, "items": items}


# ---------- manajemen absensi (admin) ----------

def _filter(args):
    mulai, selesai = params.rentang_tanggal(args)
    return {"mulai": mulai, "selesai": selesai,
            "id_pegawai": params.bilangan(args.get("id_pegawai"), "id_pegawai"),
            "status": params.pilihan(args.get("status"), "status", STATUS_KEHADIRAN)}


def list_absensi(args):
    f = _filter(args)
    page, per_page, offset = params.halaman(args)
    with get_connection().connect() as conn:
        items = [_out(a) for a in q.list_absensi(conn, f, per_page, offset)]
        total = q.count_absensi(conn, f)
    return {"items": items, "total": total, "page": page, "per_page": per_page}


def detail_absensi(id_absensi, id_pegawai_pemilik=None):
    with get_connection().connect() as conn:
        return _out(_get_absensi(conn, id_absensi, id_pegawai_pemilik))


def _isian_manual(payload, tanggal, jadwal_masuk, jadwal_pulang, toleransi):
    """Validasi status + jam, hitung menit telat / pulang cepat. Dipakai input manual & koreksi."""
    require_fields(payload, ["keterangan"])
    status = params.pilihan(payload.get("status_kehadiran"), "status_kehadiran", STATUS_KEHADIRAN,
                            default=HADIR)
    if status != HADIR:
        return {"status_kehadiran": status, "jam_masuk": None, "jam_pulang": None,
                "menit_telat": 0, "menit_pulang_cepat": 0, "keterangan": payload["keterangan"]}

    if tanggal > today_wita():
        raise AppError("TANGGAL_TIDAK_VALID", "Status HADIR tidak bisa diisi untuk tanggal yang akan datang", 400)
    jam_masuk = _waktu(tanggal, params.jam(payload.get("jam_masuk"), "jam_masuk", wajib=True))
    jam_pulang = _waktu(tanggal, params.jam(payload.get("jam_pulang"), "jam_pulang"))
    if jam_pulang and jam_pulang <= jam_masuk:
        raise AppError("PARAMETER_TIDAK_VALID", "jam_pulang harus setelah jam_masuk", 400, {"field": "jam_pulang"})
    return {"status_kehadiran": status, "jam_masuk": jam_masuk, "jam_pulang": jam_pulang,
            "menit_telat": _menit_telat(jam_masuk, tanggal, jadwal_masuk, toleransi),
            "menit_pulang_cepat": _menit_pulang_cepat(jam_pulang, tanggal, jadwal_pulang),
            "keterangan": payload["keterangan"]}


def input_manual(payload, user_id):
    payload = payload or {}
    require_fields(payload, ["id_pegawai", "tanggal", "keterangan"])
    id_pegawai = params.bilangan(payload["id_pegawai"], "id_pegawai", wajib=True)
    tanggal = params.tanggal(payload["tanggal"], "tanggal", wajib=True)
    with get_connection().begin() as conn:
        kepegawaian.get_pegawai(conn, id_pegawai)
        jadwal = _jadwal(conn)
        data = _isian_manual(payload, tanggal, jadwal["jam_masuk"], jadwal["jam_pulang"],
                             jadwal["toleransi_menit"])
        id_absensi = q.insert_manual(conn, {
            **data, "id_pegawai": id_pegawai, "tanggal": tanggal,
            "jadwal_masuk": jadwal["jam_masuk"], "jadwal_pulang": jadwal["jam_pulang"],
            "toleransi_menit": jadwal["toleransi_menit"], "user": user_id, "now": now_wita(),
        })
        if not id_absensi:
            ada = q.get_absensi_harian(conn, id_pegawai, tanggal)
            raise AppError("ABSENSI_SUDAH_ADA", "Pegawai sudah punya data absensi di tanggal ini. "
                           "Gunakan koreksi (PUT) untuk mengubahnya", 409, {"id_absensi": ada["id_absensi"]})
        baru = q.get_absensi(conn, id_absensi)
        catat_audit(conn, user_id, "INPUT_MANUAL_ABSENSI", "absensi", id_absensi, None, baru)
        return _out(baru)


def koreksi_absensi(id_absensi, payload, user_id):
    payload = payload or {}
    with get_connection().begin() as conn:
        lama = _get_absensi(conn, id_absensi)
        jadwal = _jadwal(conn)
        # pakai snapshot jadwal hari itu; fallback ke jadwal sekarang kalau kosong
        data = _isian_manual(payload, lama["tanggal"],
                             lama["jadwal_masuk"] or jadwal["jam_masuk"],
                             lama["jadwal_pulang"] or jadwal["jam_pulang"],
                             lama["toleransi_menit"] if lama["toleransi_menit"] is not None
                             else jadwal["toleransi_menit"])
        q.update_koreksi(conn, {**data, "id_absensi": id_absensi, "user": user_id, "now": now_wita()})
        baru = q.get_absensi(conn, id_absensi)
        catat_audit(conn, user_id, "KOREKSI_ABSENSI", "absensi", id_absensi, lama, baru)
        return _out(baru)


# ---------- dari modul perizinan ----------

def buat_absensi_izin(conn, izin, user_id):
    """Dipanggil di transaksi perizinan. Hari libur/non-kerja & hari yang sudah ada absensinya
    dilewati. Return (tanggal_dibuat, tanggal_dilewati)."""
    jadwal = _jadwal(conn)
    dibuat, dilewati = [], []
    tgl = izin["tanggal_mulai"]
    while tgl <= izin["tanggal_selesai"]:
        hari_kerja, _ = _cek_hari(conn, tgl, jadwal)
        if hari_kerja:
            ok = q.insert_izin(conn, {
                "id_pegawai": izin["id_pegawai"], "tanggal": tgl, "status_kehadiran": izin["jenis"],
                "id_izin": izin["id_izin"], "jadwal_masuk": jadwal["jam_masuk"],
                "jadwal_pulang": jadwal["jam_pulang"], "toleransi_menit": jadwal["toleransi_menit"],
                "keterangan": izin["alasan"], "user": user_id, "now": now_wita(),
            })
            (dibuat if ok else dilewati).append(tgl)
        tgl += timedelta(days=1)
    return dibuat, dilewati


def hapus_absensi_izin(conn, id_izin):
    """Return daftar tanggal yang dihapus."""
    return q.delete_absensi_izin(conn, id_izin)


def hapus_absensi(id_absensi, user_id):
    with get_connection().begin() as conn:
        lama = _get_absensi(conn, id_absensi)
        q.delete_absensi(conn, id_absensi)
        catat_audit(conn, user_id, "HAPUS_ABSENSI", "absensi", id_absensi, lama, None)


def path_foto_absensi(id_absensi, tipe, id_pegawai_pemilik=None):
    tipe = params.pilihan(tipe, "tipe", [MASUK, PULANG], wajib=True)
    with get_connection().connect() as conn:
        absensi = _get_absensi(conn, id_absensi, id_pegawai_pemilik)
    foto = absensi["foto_masuk" if tipe == MASUK else "foto_pulang"]
    if not foto:
        raise AppError("FILE_TIDAK_DITEMUKAN", f"Tidak ada foto absen {tipe.lower()}", 404)
    return storage.absolute_path(foto)


# ---------- percobaan absen gagal ----------

def list_percobaan(args):
    mulai, selesai = params.rentang_tanggal(args)
    f = {"mulai": mulai, "selesai": selesai, "id_pegawai": params.bilangan(args.get("id_pegawai"), "id_pegawai")}
    page, per_page, offset = params.halaman(args)
    with get_connection().connect() as conn:
        items = q.list_percobaan(conn, f, per_page, offset)
        total = q.count_percobaan(conn, f)
    for x in items:
        x["foto_url"] = f"/api/absensi/percobaan/{x['id_percobaan']}/foto" if x["foto_path"] else None
    return {"items": items, "total": total, "page": page, "per_page": per_page}


def path_foto_percobaan(id_percobaan):
    with get_connection().connect() as conn:
        foto = q.get_foto_percobaan(conn, id_percobaan)
    if not foto:
        raise AppError("FILE_TIDAK_DITEMUKAN", "Foto tidak ditemukan", 404)
    return storage.absolute_path(foto)


# ---------- hari libur ----------

def list_hari_libur(args):
    tahun = params.bilangan(args.get("tahun"), "tahun", default=today_wita().year, minimal=2000, maksimal=2100)
    with get_connection().connect() as conn:
        return q.list_hari_libur(conn, date(tahun, 1, 1), date(tahun, 12, 31))


def _get_hari_libur(conn, tanggal):
    libur = q.get_hari_libur(conn, tanggal)
    if not libur:
        raise AppError("HARI_LIBUR_TIDAK_DITEMUKAN", "Hari libur tidak ditemukan", 404)
    return libur


def tambah_hari_libur(payload, user_id):
    payload = payload or {}
    require_fields(payload, ["tanggal", "keterangan"])
    tanggal = params.tanggal(payload["tanggal"], "tanggal", wajib=True)
    with get_connection().begin() as conn:
        if not q.insert_hari_libur(conn, {"tanggal": tanggal, "keterangan": payload["keterangan"],
                                          "user": user_id, "now": now_wita()}):
            raise AppError("HARI_LIBUR_SUDAH_ADA", f"Tanggal {tanggal} sudah terdaftar sebagai hari libur", 409)
        baru = q.get_hari_libur(conn, tanggal)
        catat_audit(conn, user_id, "TAMBAH_HARI_LIBUR", "hari_libur", None, None, baru)
        return baru


def ubah_hari_libur(tanggal, payload, user_id):
    tanggal = params.tanggal(tanggal, "tanggal", wajib=True)
    require_fields(payload, ["keterangan"])
    with get_connection().begin() as conn:
        lama = _get_hari_libur(conn, tanggal)
        q.update_hari_libur(conn, tanggal, payload["keterangan"])
        baru = q.get_hari_libur(conn, tanggal)
        catat_audit(conn, user_id, "UBAH_HARI_LIBUR", "hari_libur", None, lama, baru)
        return baru


def hapus_hari_libur(tanggal, user_id):
    tanggal = params.tanggal(tanggal, "tanggal", wajib=True)
    with get_connection().begin() as conn:
        lama = _get_hari_libur(conn, tanggal)
        q.delete_hari_libur(conn, tanggal)
        catat_audit(conn, user_id, "HAPUS_HARI_LIBUR", "hari_libur", None, lama, None)
