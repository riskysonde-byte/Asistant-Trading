"""Tes backend penyimpanan: Supabase (server palsu) dan Lokal harus berperilaku sama."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_supabase  # noqa: E402
import penyimpan  # noqa: E402
import rekam  # noqa: E402

LEVEL = {'beli_dari': 98, 'beli_sampai': 100, 'tp': 110, 'sl': 95}


@pytest.fixture(params=['supabase', 'lokal'])
def db(request, tmp_path):
    if request.param == 'supabase':
        srv = fake_supabase.Server()
        yield penyimpan.Supabase(srv.url, fake_supabase.KUNCI)
        srv.tutup()
    else:
        yield penyimpan.Lokal(str(tmp_path))


def test_kv(db):
    assert db.kv_get('x', 'kosong') == 'kosong'
    db.kv_set('x', {'a': [1, 2], 'b': 'teks'})
    assert db.kv_get('x') == {'a': [1, 2], 'b': 'teks'}
    db.kv_set('x', 5)
    assert db.kv_get('x') == 5


def test_sinyal_upsert_dan_filter(db):
    a = rekam.buat_sinyal('kantor', 'BBCA', LEVEL, gaya='Swing', putusan='BELI', tanggal='2026-01-05')
    b = rekam.buat_sinyal('kantor', 'TLKM', LEVEL, gaya='Trading', putusan='TUNGGU', tanggal='2026-01-06')
    db.sinyal_upsert([a, b])
    db.sinyal_upsert([a])                                              # upsert tidak menggandakan
    assert len(db.sinyal_semua()) == 2
    assert db.sinyal_semua()[0]['kode'] == 'TLKM'                      # terbaru dulu
    a2 = dict(a, status='kena_tp', hasil_pct=10.0)
    db.sinyal_upsert([a2])
    assert [x['kode'] for x in db.sinyal_aktif()] == ['TLKM']          # yang final tidak lagi aktif
    assert {x['kode']: x['status'] for x in db.sinyal_semua()}['BBCA'] == 'kena_tp'
    db.sinyal_upsert([])                                               # kosong aman


def test_skor(db):
    db.skor_upsert([rekam.buat_skor('BBCA', 80, 'BULLISH', 9000, tanggal='2026-01-05')])
    db.skor_upsert([dict(rekam.buat_skor('BBCA', 80, 'BULLISH', 9000, tanggal='2026-01-05'), ret5=3.2)])
    semua = db.skor_semua()
    assert len(semua) == 1 and semua[0]['ret5'] == 3.2


def test_kolom_asing_dibuang_agar_tidak_ditolak_database():
    srv = fake_supabase.Server()
    try:
        d = penyimpan.Supabase(srv.url, fake_supabase.KUNCI)
        x = dict(rekam.buat_sinyal('kantor', 'BBCA', LEVEL, tanggal='2026-01-05'), kolom_ngawur='x')
        d.sinyal_upsert([x])
        assert 'kolom_ngawur' not in d.sinyal_semua()[0]
    finally:
        srv.tutup()


def test_supabase_kunci_salah_memberi_error_jelas():
    srv = fake_supabase.Server()
    try:
        with pytest.raises(RuntimeError, match='401'):
            penyimpan.Supabase(srv.url, 'salah').kv_get('x')
    finally:
        srv.tutup()


def test_dari_env():
    assert penyimpan.dari_env({}) is None
    assert penyimpan.dari_env({'SUPABASE_URL': 'https://a.supabase.co'}) is None
    assert penyimpan.dari_env({'SUPABASE_URL': 'https://a.supabase.co/', 'SUPABASE_KEY': 'k'}).url == 'https://a.supabase.co'
