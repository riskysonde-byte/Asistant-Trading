"""Tes tugas terjadwal dengan semua akses luar (Yahoo, Telegram) digantikan tiruan."""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tugas'))
import pantau  # noqa: E402
import penyimpan  # noqa: E402
import rekam  # noqa: E402

LEVEL = {'beli_dari': 98, 'beli_sampai': 100, 'tp': 110, 'sl': 95}
HARI = '2026-01-12'


def bars(baris, mulai='2026-01-06'):
    return pd.DataFrame(baris, index=pd.bdate_range(mulai, periods=len(baris)), columns=['Open', 'High', 'Low', 'Close'])


class Tiruan:
    def __init__(self, harian=None, harga=None, ihsg=None, gagal=False):
        self.harian_data, self.harga, self.ihsg_nilai, self.gagal = harian or {}, harga or {}, ihsg, gagal
        self.pesan = []

    def kirim(self, teks):
        if self.gagal:
            return False, 'gagal'
        self.pesan.append(teks)
        return True, 'terkirim'

    def jalankan(self, mode, db):
        return pantau.jalankan(mode, db, self.kirim, lambda ks, p='3mo': {k: self.harian_data[k] for k in ks if k in self.harian_data},
                               lambda ks: {k: self.harga[k] for k in ks if k in self.harga}, lambda: self.ihsg_nilai, HARI)


def sinyal(kode, **kw):
    return dict(rekam.buat_sinyal('kantor', kode, LEVEL, gaya='Swing', putusan='BELI', tanggal='2026-01-05'), **kw)


def test_tp_kena_dan_tidak_dikirim_dua_kali(tmp_path):
    db = penyimpan.Lokal(str(tmp_path))
    db.sinyal_upsert([sinyal('BBCA')])
    t = Tiruan(harian={'BBCA': bars([(101, 103, 99, 102), (102, 112, 101, 111)])})
    r = t.jalankan('intraday', db)
    assert r['terkirim'] and r['pesan'] == 1 and 'TP KENA' in t.pesan[0] and '+10.00%' in t.pesan[0]
    assert db.sinyal_semua()[0]['status'] == 'kena_tp' and db.sinyal_aktif() == []
    t2 = Tiruan()
    assert t2.jalankan('intraday', db)['pesan'] == 0 and t2.pesan == []       # sudah final, tidak diulang


def test_dekat_zona_sekali_per_hari(tmp_path):
    db = penyimpan.Lokal(str(tmp_path))
    db.sinyal_upsert([sinyal('TLKM')])
    t = Tiruan(harian={'TLKM': bars([(105, 107, 103, 106)])}, harga={'TLKM': 100.2})
    assert t.jalankan('intraday', db)['pesan'] == 1 and 'zona beli' in t.pesan[0]
    assert t.jalankan('intraday', db)['pesan'] == 0 and len(t.pesan) == 1     # putaran kedua: tidak ada pesan baru
    assert db.sinyal_aktif()[0]['harga_terakhir'] == 106


def test_alert_harga_dan_ihsg(tmp_path):
    db = penyimpan.Lokal(str(tmp_path))
    db.kv_set('alert', [{'id': 'a1', 'kode': 'ASII', 'op': '>=', 'harga': 5000, 'aktif': True},
                        {'id': 'a2', 'kode': 'BBRI', 'op': '<=', 'harga': 4000, 'aktif': True}])
    t = Tiruan(harga={'ASII': 5100, 'BBRI': 4500}, ihsg=-2.1)
    r = t.jalankan('intraday', db)
    teks = '\n'.join(t.pesan)
    assert 'ASII' in teks and 'BBRI' not in teks and 'IHSG turun' in teks and r['pesan'] == 2
    assert {a['id']: a.get('dikirim') for a in db.kv_get('alert')} == {'a1': HARI, 'a2': None}
    t.pesan.clear()
    t.jalankan('intraday', db)
    assert t.pesan == []                                                       # alert sekali kirim, IHSG sekali per hari


def test_telegram_gagal_status_tidak_disimpan_lalu_dicoba_ulang(tmp_path):
    db = penyimpan.Lokal(str(tmp_path))
    db.sinyal_upsert([sinyal('BBCA')])
    data = {'BBCA': bars([(101, 112, 99, 111)])}
    r = Tiruan(harian=data, gagal=True).jalankan('intraday', db)
    assert not r['terkirim'] and db.sinyal_aktif()[0]['status'] == 'belum_masuk'
    ok = Tiruan(harian=data)
    assert ok.jalankan('intraday', db)['terkirim'] and 'TP KENA' in ok.pesan[0]


def test_ringkasan_harian_dan_validasi_skor(tmp_path):
    db = penyimpan.Lokal(str(tmp_path))
    db.sinyal_upsert([sinyal('BBCA')])
    snap = [dict(rekam.buat_skor(k, s, lab, 100, tanggal='2026-01-02')) for k, s, lab in
            (('AAAA', 80, 'BULLISH'), ('BBBB', -80, 'BEARISH'))]
    db.skor_upsert(snap)
    naik = pd.DataFrame({'Close': [101 + i for i in range(14)]}, index=pd.bdate_range('2026-01-05', periods=14))
    turun = pd.DataFrame({'Close': [99 - i for i in range(14)]}, index=pd.bdate_range('2026-01-05', periods=14))
    t = Tiruan(harian={'BBCA': bars([(101, 112, 99, 111)]), 'AAAA': naik, 'BBBB': turun})
    r = t.jalankan('harian', db)
    teks = t.pesan[0]
    assert 'Ringkasan harian' in teks and 'win rate 100.0%' in teks and 'BULLISH +5.00%' in teks and 'BEARISH -5.00%' in teks
    assert {x['kode']: x['ret5'] for x in db.skor_semua()} == {'AAAA': 5.0, 'BBBB': -5.0}
    assert r['skor']['per_label']['BULLISH']['rata_ret5'] == 5.0


def test_main_tanpa_rahasia_keluar_dengan_tenang(monkeypatch, capsys):
    for k in ('SUPABASE_URL', 'SUPABASE_KEY', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID'):
        monkeypatch.delenv(k, raising=False)
    assert pantau.main(['pantau.py', 'intraday']) == 0
    assert 'dilewati' in capsys.readouterr().out
    assert pantau.main(['pantau.py', 'ngawur']) == 2
