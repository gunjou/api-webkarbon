"""
Render surat: template_isi (dari DB, bisa diedit admin) dirender di SANDBOX,
lalu disisipkan ke templates/layout.html (kop, judul, nomor, data diri, keperluan, ttd).
"""
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from jinja2.sandbox import SandboxedEnvironment
from markupsafe import Markup

BULAN = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
         "Agustus", "September", "Oktober", "November", "Desember"]
JENIS_KELAMIN = {"L": "Laki-Laki", "P": "Perempuan"}


def tanggal_indo(value):
    if not value:
        return ""
    if isinstance(value, str):
        value = date.fromisoformat(value[:10])
    return f"{value.day} {BULAN[value.month]} {value.year}"


def _filters(env):
    env.filters["tanggal"] = tanggal_indo
    env.filters["jk"] = lambda v: JENIS_KELAMIN.get(v, v or "")
    return env


_layout_env = _filters(Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
))
_sandbox_env = _filters(SandboxedEnvironment(autoescape=True))


def render_html(jenis, surat_data, desa, penandatangan, nomor_surat=None, tanggal_surat=None,
                logo_uri=None):
    """
    jenis          : row jenis_surat (judul_surat, pakai_subjek, template_isi)
    surat_data     : surat.data (subjek, keperluan, isian)
    desa           : pengaturan 'desa'
    penandatangan  : {"nama","jabatan","mode"} atau None
    nomor_surat    : None saat preview
    """
    ctx = {
        "subjek": surat_data.get("subjek") or {},
        "isian": surat_data.get("isian") or {},
        "keperluan": surat_data.get("keperluan"),
        "desa": desa,
    }
    isi = _sandbox_env.from_string(jenis["template_isi"]).render(**ctx)

    return _layout_env.get_template("layout.html").render(
        **ctx,
        judul=jenis["judul_surat"],
        pakai_subjek=jenis["pakai_subjek"],
        isi=Markup(isi),
        nomor_surat=nomor_surat,
        tanggal_surat=tanggal_surat or date.today(),
        penandatangan=penandatangan,
        logo_uri=logo_uri,
    )


def render_pdf(html, base_url=None) -> bytes:
    # import di sini supaya app tetap bisa jalan walau library sistem WeasyPrint belum terpasang
    from weasyprint import HTML
    return HTML(string=html, base_url=base_url).write_pdf()
