"""
Setiap endpoint wajib diberi label pemakai di awal judul Swagger (baris pertama docstring):
  (pegawai)          -> dipakai aplikasi pegawai, data milik sendiri
  (admin)            -> panel admin: ADMIN / OPERATOR / KADES
  (pegawai & admin)  -> cukup login, dipakai keduanya
  (publik)           -> tanpa token, mis. login
"""
from app import create_app

LABEL = ("(pegawai) ", "(admin) ", "(pegawai & admin) ", "(publik) ")
METHODS = {"get", "post", "put", "patch", "delete"}


def test_semua_endpoint_berlabel():
    spec = create_app().test_client().get("/api/swagger.json").get_json()
    tanpa_label = [
        f"{method.upper()} {path}: {op.get('summary')!r}"
        for path, ops in spec["paths"].items()
        for method, op in ops.items()
        if method in METHODS and not (op.get("summary") or "").startswith(LABEL)
    ]
    assert not tanpa_label, "Endpoint tanpa label (pegawai)/(admin)/(pegawai & admin)/(publik):\n" + \
        "\n".join(tanpa_label)
