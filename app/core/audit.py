import json

from sqlalchemy import text

from app.core.db import json_default, now_wita


def catat_audit(conn, id_user, aksi, entitas, id_entitas=None, data_lama=None, data_baru=None):
    """Dipanggil di dalam transaksi yang sama dengan perubahan datanya."""
    conn.execute(text("""
        INSERT INTO audit_log (id_user, aksi, entitas, id_entitas, data_lama, data_baru, created_at)
        VALUES (:id_user, :aksi, :entitas, :id_entitas,
                CAST(:data_lama AS jsonb), CAST(:data_baru AS jsonb), :now)
    """), {
        "id_user": id_user,
        "aksi": aksi,
        "entitas": entitas,
        "id_entitas": id_entitas,
        "data_lama": json.dumps(data_lama, default=json_default) if data_lama is not None else None,
        "data_baru": json.dumps(data_baru, default=json_default) if data_baru is not None else None,
        "now": now_wita(),
    })
