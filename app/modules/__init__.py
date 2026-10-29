from app.modules import (absensi, admin, auth, kepegawaian, kependudukan, lokasi_absen, pengaturan,
                         perizinan, persuratan)

# Urutan = urutan tampil di Swagger. Modul baru cukup ditambahkan di sini.
MODULES = [
    auth,
    admin,
    pengaturan,
    kepegawaian,
    kependudukan,
    persuratan,
    lokasi_absen,
    absensi,
    perizinan,
]
