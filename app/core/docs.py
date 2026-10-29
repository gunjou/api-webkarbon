"""
Helper dokumentasi Swagger (flask-restx).

Semua helper di sini HANYA untuk dokumentasi: @ns.response tidak memfilter/mengubah
response, jadi routes tetap mengembalikan {"data": ...} apa adanya.

Pemakaian di routes.py:
    pegawai_out = ns.model("PegawaiDetail", {...})

    @ns.response(200, "OK", docs.envelope(ns, pegawai_out))
    @docs.errors(ns, 401, 403, 404)
    def get(self, id_pegawai): ...
"""
from flask_restx import Model, fields

error_detail_model = Model("ErrorDetail", {
    "code": fields.String(example="FIELD_WAJIB_KOSONG"),
    "message": fields.String(example="Field wajib belum diisi: nama"),
    "details": fields.Raw(description="Informasi tambahan (opsional), mis. {\"fields\": [...]}"),
})

error_model = Model("Error", {
    "error": fields.Nested(error_detail_model),
})

message_model = Model("Message", {
    "message": fields.String(example="Data dihapus"),
})

ERROR_DESC = {
    400: "Input tidak valid / field wajib kosong",
    401: "Belum login, token tidak valid, atau token kedaluwarsa",
    403: "Role tidak memiliki akses ke fitur ini",
    404: "Data tidak ditemukan",
    409: "Data bertentangan dengan data yang sudah ada",
}


def _add(ns, *models):
    for m in models:
        ns.add_model(m.name, m)


def envelope(ns, model):
    """{"data": <model>}"""
    return ns.model(f"{model.name}Response", {"data": fields.Nested(model)})


def envelope_list(ns, model):
    """{"data": [<model>, ...]}"""
    return ns.model(f"{model.name}ListResponse", {"data": fields.List(fields.Nested(model))})


def paginated(ns, model):
    """{"data": {"items": [...], "total", "page", "per_page"}}"""
    page = ns.model(f"{model.name}Page", {
        "items": fields.List(fields.Nested(model)),
        "total": fields.Integer(example=120),
        "page": fields.Integer(example=1),
        "per_page": fields.Integer(example=20),
    })
    return ns.model(f"{model.name}PageResponse", {"data": fields.Nested(page)})


def message(ns):
    """{"data": {"message": "..."}}"""
    _add(ns, message_model)
    return ns.model("MessageResponse", {"data": fields.Nested(message_model)})


def errors(ns, *codes):
    """Dekorator: dokumentasikan response error standar {"error": {...}}."""
    _add(ns, error_detail_model, error_model)

    def decorator(fn):
        for code in codes:
            fn = ns.response(code, ERROR_DESC[code], error_model)(fn)
        return fn
    return decorator
