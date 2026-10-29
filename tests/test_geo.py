from app.modules.absensi.geo import jarak_meter, lokasi_terdekat

KANTOR = {"id_lokasi": 1, "nama": "Kantor Desa", "latitude": -8.6200, "longitude": 116.1000,
          "radius_meter": 100}


def test_jarak_titik_sama_nol():
    assert jarak_meter(-8.62, 116.1, -8.62, 116.1) == 0


def test_jarak_sekitar_111_meter_per_0_001_derajat_lintang():
    assert 110 < jarak_meter(-8.620, 116.1, -8.621, 116.1) < 112


def test_di_dalam_radius():
    lok, jarak, di_dalam = lokasi_terdekat(-8.6203, 116.1002, [KANTOR])
    assert lok["id_lokasi"] == 1 and di_dalam and jarak < 100


def test_di_luar_radius():
    _, jarak, di_dalam = lokasi_terdekat(-8.6300, 116.1000, [KANTOR])
    assert not di_dalam and jarak > 1000


def test_tanpa_lokasi():
    assert lokasi_terdekat(-8.62, 116.1, []) == (None, None, False)
