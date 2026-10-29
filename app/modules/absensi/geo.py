from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_M = 6_371_000


def jarak_meter(lat1, lng1, lat2, lng2):
    """Jarak dua titik (haversine), dalam meter."""
    lat1, lng1, lat2, lng2 = map(lambda v: radians(float(v)), (lat1, lng1, lat2, lng2))
    dlat, dlng = lat2 - lat1, lng2 - lng1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(a))


def lokasi_terdekat(lat, lng, daftar_lokasi):
    """
    daftar_lokasi: list dict {id_lokasi, nama, latitude, longitude, radius_meter}
    Return (lokasi, jarak, di_dalam_radius) untuk lokasi terdekat, atau (None, None, False).
    """
    terdekat, jarak_min = None, None
    for lok in daftar_lokasi:
        j = jarak_meter(lat, lng, lok["latitude"], lok["longitude"])
        if jarak_min is None or j < jarak_min:
            terdekat, jarak_min = lok, j
    if terdekat is None:
        return None, None, False
    return terdekat, jarak_min, jarak_min <= terdekat["radius_meter"]
