"""
Modul shared. Modul lain (absensi, persuratan, payroll nanti) memakai fungsi
get_pegawai(conn, id) & get_embedding_wajah(conn, id) di bawah, bukan query langsung
ke tabel pegawai / wajah_pegawai.
"""
from app.core import face, storage
from app.core.audit import catat_audit
from app.core.db import get_connection, now_wita
from app.core.errors import AppError, require_fields

from . import queries as q

FIELDS = ["nama", "nik", "jabatan", "no_hp", "tanggal_mulai"]


PESAN_WAJAH = {
    "FOTO_TIDAK_VALID": "File bukan gambar yang valid (gunakan JPG/PNG)",
    "WAJAH_TIDAK_TERDETEKSI": "Wajah tidak terdeteksi. Pastikan wajah terlihat jelas & pencahayaan cukup",
    "WAJAH_LEBIH_DARI_SATU": "Terdeteksi lebih dari satu wajah. Pastikan hanya satu orang di foto",
}


def url_foto_wajah(id_pegawai, id_wajah):
    """Dipakai lintas modul (admin/users). ?v= berubah tiap foto diganti, jadi cache browser
    otomatis ter-refresh. None kalau belum ada wajah."""
    return f"/api/pegawai/{id_pegawai}/wajah/foto?v={id_wajah}" if id_wajah else None


def _foto_wajah(pegawai):
    """Tambah foto_wajah_url (GET dengan header Authorization), None kalau belum ada wajah."""
    return {**pegawai, "foto_wajah_url": url_foto_wajah(pegawai["id_pegawai"], pegawai["id_wajah"])}


def get_pegawai(conn, id_pegawai):
    """Dipakai lintas modul. Raise 404 kalau tidak ada."""
    pegawai = q.get_pegawai_by_id(conn, id_pegawai)
    if not pegawai:
        raise AppError("PEGAWAI_TIDAK_DITEMUKAN", "Data pegawai tidak ditemukan", 404)
    return _foto_wajah(pegawai)


def list_pegawai_aktif(conn):
    """Dipakai lintas modul (absensi: monitor harian & rekap). Semua pegawai aktif, urut nama."""
    return [_foto_wajah(p) for p in q.list_pegawai(conn)]


def list_pegawai(keyword=None):
    with get_connection().connect() as conn:
        return [_foto_wajah(p) for p in q.list_pegawai(conn, keyword or None)]


def pegawai_saya(id_pegawai):
    """Data diri pegawai yang login. foto_wajah_url ke endpoint /me (bukan endpoint admin)."""
    with get_connection().connect() as conn:
        pegawai = get_pegawai(conn, id_pegawai)
    id_wajah = pegawai["id_wajah"]
    return {**pegawai, "wajah_terdaftar": id_wajah is not None,
            "foto_wajah_url": f"/api/pegawai/me/wajah/foto?v={id_wajah}" if id_wajah else None}


def detail_pegawai(id_pegawai):
    with get_connection().connect() as conn:
        return get_pegawai(conn, id_pegawai)


def tambah_pegawai(payload, user_id):
    """Tambah pegawai. Kalau payload berisi `akun`, user login ikut dibuat dalam satu
    transaksi: gagal salah satu, keduanya batal."""
    # import di sini karena modul admin meng-import modul ini (hindari circular import)
    from app.modules.admin import service as admin

    require_fields(payload, ["nama", "jabatan"])
    data = {k: (payload.get(k) or None) for k in FIELDS}
    akun = payload.get("akun")
    if akun is not None and not isinstance(akun, dict):
        raise AppError("AKUN_TIDAK_VALID", "Field akun harus berupa object", 400)

    with get_connection().begin() as conn:
        id_pegawai = q.insert_pegawai(conn, {**data, "user": user_id, "now": now_wita()})
        pegawai = get_pegawai(conn, id_pegawai)
        if akun:
            pegawai["akun"] = admin.buat_user(conn, {
                **akun,
                "nama": akun.get("nama") or data["nama"],
                "role": akun.get("role") or admin.PEGAWAI,
                "id_pegawai": id_pegawai,
            }, user_id)
        else:
            pegawai["akun"] = None
        return pegawai


def ubah_pegawai(id_pegawai, payload, user_id):
    require_fields(payload, ["nama", "jabatan"])
    data = {k: (payload.get(k) or None) for k in FIELDS}
    with get_connection().begin() as conn:
        lama = get_pegawai(conn, id_pegawai)
        q.update_pegawai(conn, {**data, "id_pegawai": id_pegawai, "user": user_id, "now": now_wita()})
        baru = get_pegawai(conn, id_pegawai)
        catat_audit(conn, user_id, "UBAH_PEGAWAI", "pegawai", id_pegawai, lama, baru)
        return baru


def hapus_pegawai(id_pegawai, user_id):
    with get_connection().begin() as conn:
        lama = get_pegawai(conn, id_pegawai)
        q.soft_delete_pegawai(conn, id_pegawai, user_id, now_wita())
        catat_audit(conn, user_id, "HAPUS_PEGAWAI", "pegawai", id_pegawai, lama, None)


# ---------- wajah pegawai (1 wajah aktif per pegawai) ----------

def get_embedding_wajah(conn, id_pegawai):
    """Dipakai modul absensi untuk verifikasi. Return list[float] atau None kalau belum ada wajah."""
    return q.get_embedding_wajah(conn, id_pegawai)


def _wajah_out(wajah):
    return {**wajah, "foto_url": url_foto_wajah(wajah["id_pegawai"], wajah["id_wajah"])}


def simpan_wajah(id_pegawai, file, user_id):
    """Tambah atau ganti wajah pegawai. Return (wajah, dibuat_baru)."""
    if not file or not file.filename:
        raise AppError("FILE_KOSONG", "Foto belum dipilih (field multipart: foto)", 400)
    with get_connection().connect() as conn:
        get_pegawai(conn, id_pegawai)  # 404 lebih dulu, sebelum proses foto yang berat
    try:
        embedding, jpeg = face.proses_enroll(file.read())
    except ValueError as e:
        kode = str(e)
        raise AppError(kode, PESAN_WAJAH.get(kode, kode), 400)

    with get_connection().begin() as conn:
        get_pegawai(conn, id_pegawai)
        q.kunci_pegawai(conn, id_pegawai)
        lama = q.get_wajah(conn, id_pegawai)
        q.soft_delete_wajah(conn, id_pegawai)
        id_wajah = q.insert_wajah(conn, {
            "id_pegawai": id_pegawai, "embedding": embedding,
            "foto_path": storage.save_bytes(jpeg, "wajah", "jpg"),
            "user": user_id, "now": now_wita(),
        })
        baru = q.get_wajah(conn, id_pegawai)
        catat_audit(conn, user_id, "GANTI_WAJAH" if lama else "TAMBAH_WAJAH",
                    "wajah_pegawai", id_wajah, lama, baru)
        return _wajah_out(baru), lama is None


def hapus_wajah(id_pegawai, user_id):
    with get_connection().begin() as conn:
        get_pegawai(conn, id_pegawai)
        lama = q.get_wajah(conn, id_pegawai)
        if not lama:
            raise AppError("WAJAH_TIDAK_DITEMUKAN", "Pegawai belum punya foto wajah", 404)
        q.soft_delete_wajah(conn, id_pegawai)
        catat_audit(conn, user_id, "HAPUS_WAJAH", "wajah_pegawai", lama["id_wajah"], lama, None)


def path_foto_wajah(id_pegawai):
    """Path absolut file foto wajah aktif (untuk ditampilkan di frontend)."""
    with get_connection().connect() as conn:
        wajah = q.get_wajah(conn, id_pegawai)
    if not wajah:
        raise AppError("WAJAH_TIDAK_DITEMUKAN", "Pegawai belum punya foto wajah", 404)
    return storage.absolute_path(wajah["foto_path"])
