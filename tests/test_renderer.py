import pytest
from jinja2.exceptions import SecurityError

from app.modules.persuratan.renderer import render_html, tanggal_indo

DESA = {"nama": "Karang Bongkot", "kecamatan": "Labuapi", "kabupaten": "Lombok Barat",
        "alamat": "Jln. Gunung Pengsong No. 1", "kode_pos": "83361"}
JENIS = {"judul_surat": "SURAT KETERANGAN BELUM MENIKAH", "pakai_subjek": True,
         "template_isi": "<p>Adalah penduduk Desa {{ desa.nama }}.</p>"}
DATA = {"subjek": {"nik": "5201000000000001", "nama": "Contoh Nama", "tempat_lahir": "Mataram",
                   "tgl_lahir": "1998-11-03", "jenis_kelamin": "L",
                   "alamat_lengkap": "Dusun Perampuan RT 002"},
        "keperluan": "pengajuan pinjaman di Bank", "isian": {}}


def test_tanggal_indo():
    assert tanggal_indo("2026-08-24") == "24 Agustus 2026"


def test_render_surat_berisi_data_utama():
    html = render_html(JENIS, DATA, DESA,
                       {"nama": "Kaharudin", "jabatan": "Sekretaris Desa", "mode": "AN"},
                       nomor_surat="148.1/180/KRB/2026")
    assert "148.1/180/KRB/2026" in html
    assert "CONTOH NAMA" in html
    assert "3 November 1998" in html
    assert "Laki-Laki" in html
    assert "a.n Kepala Desa Karang Bongkot" in html
    assert "pengajuan pinjaman di Bank" in html


def test_template_dari_db_disandbox():
    jahat = {**JENIS, "template_isi": "{{ ''.__class__.__mro__[1].__subclasses__() }}"}
    with pytest.raises(SecurityError):
        render_html(jahat, DATA, DESA, None)
