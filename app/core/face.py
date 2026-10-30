"""
Face recognition (verifikasi 1:1) + crop/kompres foto wajah untuk enrollment.
Model dimuat sekali per worker (lazy), bukan per request.

Dependensi (lihat requirements.txt):
    dlib-bin               -> dlib versi wheel, tidak perlu compile/cmake
    face_recognition_models -> file model .dat (sama dengan library face_recognition)
    numpy, pillow
Embedding 128 dimensi & jarak euclidean, sama persis dengan library face_recognition,
jadi threshold 0.5 di pengaturan 'absensi' tetap berlaku.
Kalau akurasi kurang di pencahayaan buruk, ganti isi file ini ke InsightFace;
modul lain tidak perlu berubah karena antarmukanya tetap encode(), verify(), proses_enroll()
& proses_absen().
"""
import io

_models = None

MAKS_SISI_DETEKSI = 1024   # foto besar dikecilkan dulu supaya deteksi cepat
UKURAN_CROP = 300          # foto wajah tersimpan: 300x300 px
KUALITAS_JPEG = 80         # hasil ~15-30 KB per foto
MARGIN_CROP = 0.4          # tambahan area di sekitar kotak wajah (40%)


def _load():
    global _models
    if _models is None:
        import importlib.util
        from pathlib import Path

        import dlib  # noqa: import berat, sengaja lazy

        # Cari folder paket tanpa meng-import-nya: __init__ face_recognition_models
        # butuh pkg_resources (setuptools) yang tidak selalu ada di venv Python 3.12.
        spec = importlib.util.find_spec("face_recognition_models")
        base = Path(spec.submodule_search_locations[0]) / "models"
        _models = {
            "detector": dlib.get_frontal_face_detector(),
            "shape": dlib.shape_predictor(str(base / "shape_predictor_5_face_landmarks.dat")),
            "encoder": dlib.face_recognition_model_v1(str(base / "dlib_face_recognition_resnet_model_v1.dat")),
        }
    return _models


def _buka_gambar(image_bytes):
    """Bytes -> PIL RGB, orientasi EXIF dari HP sudah dibetulkan, sisi terpanjang <= MAKS_SISI_DETEKSI."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise ValueError("FOTO_TIDAK_VALID")
    img.thumbnail((MAKS_SISI_DETEKSI, MAKS_SISI_DETEKSI))
    return img


def _deteksi(img):
    """Return (array numpy, kotak wajah dlib). Raise ValueError bila wajah 0 atau > 1."""
    import numpy as np

    m = _load()
    arr = np.asarray(img)
    wajah = m["detector"](arr, 1)
    if len(wajah) == 0:
        raise ValueError("WAJAH_TIDAK_TERDETEKSI")
    if len(wajah) > 1:
        raise ValueError("WAJAH_LEBIH_DARI_SATU")
    return arr, wajah[0]


def _embedding(arr, kotak):
    m = _load()
    return list(m["encoder"].compute_face_descriptor(arr, m["shape"](arr, kotak)))


def encode(image_bytes):
    """
    Return embedding (list[float], 128 dimensi) dari foto.
    Raise ValueError bila foto tidak valid, tidak ada wajah, atau lebih dari satu wajah.
    """
    arr, kotak = _deteksi(_buka_gambar(image_bytes))
    return _embedding(arr, kotak)


def proses_enroll(image_bytes):
    """
    Untuk enrollment: return (embedding, jpeg_bytes).
    jpeg_bytes = crop persegi di sekitar wajah, UKURAN_CROP px, kualitas KUALITAS_JPEG.
    Embedding dihitung dari foto asli (bukan hasil crop) supaya akurasinya maksimal.
    """
    img = _buka_gambar(image_bytes)
    arr, kotak = _deteksi(img)
    embedding = _embedding(arr, kotak)

    cx, cy = (kotak.left() + kotak.right()) / 2, (kotak.top() + kotak.bottom()) / 2
    sisi = max(kotak.width(), kotak.height()) * (1 + 2 * MARGIN_CROP)
    sisi = min(sisi, img.width, img.height)
    left = min(max(cx - sisi / 2, 0), img.width - sisi)
    top = min(max(cy - sisi / 2, 0), img.height - sisi)
    crop = img.crop((int(left), int(top), int(left + sisi), int(top + sisi)))
    crop = crop.resize((UKURAN_CROP, UKURAN_CROP))

    out = io.BytesIO()
    crop.save(out, format="JPEG", quality=KUALITAS_JPEG, optimize=True)
    return embedding, out.getvalue()


def proses_absen(image_bytes, embedding_terdaftar, threshold=0.5):
    """
    Untuk absen: return (cocok: bool, jarak: float, jpeg_bytes).
    jpeg_bytes = crop wajah terkompres (sama seperti enrollment), disimpan sebagai bukti absen.
    Raise ValueError bila foto tidak valid, tidak ada wajah, atau lebih dari satu wajah.
    """
    import numpy as np
    embedding, jpeg = proses_enroll(image_bytes)
    jarak = float(np.linalg.norm(np.array(embedding_terdaftar) - np.array(embedding)))
    return jarak <= threshold, jarak, jpeg


def verify(image_bytes, embeddings, threshold=0.5):
    """
    Bandingkan foto dengan semua embedding milik SATU pegawai.
    Return (cocok: bool, jarak_terbaik: float). Jarak makin kecil makin mirip.
    """
    import numpy as np
    probe = np.array(encode(image_bytes))
    known = np.array(embeddings)
    jarak = float(np.min(np.linalg.norm(known - probe, axis=1)))
    return jarak <= threshold, jarak
