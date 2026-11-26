"""Tes logika rekam jejak. Jalankan: python -m pytest tests -q"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rekam  # noqa: E402

LEVEL = {'beli_dari': 98, 'beli_sampai': 100, 'tp': 110, 'sl': 95}


def sinyal(gaya='Swing', tanggal='2026-01-05'):
    return rekam.buat_sinyal('kantor', 'BBCA', LEVEL, gaya=gaya, putusan='BELI', keyakinan=8, rr=2.0, tanggal=tanggal)


def harian(baris, mulai='2026-01-06'):
    """baris: [(open, high, low, close), ...] mulai hari bursa setelah sinyal (hari kerja)."""
    idx = pd.bdate_range(mulai, periods=len(baris))
    return pd.DataFrame(baris, index=idx, columns=['Open', 'High', 'Low', 'Close'])


def test_kena_tp():
    s = rekam.evaluasi(sinyal(), harian([(101, 103, 99, 102), (102, 112, 101, 111)]))
    assert s['status'] == 'kena_tp' and s['harga_masuk'] == 100 and s['harga_keluar'] == 110
    assert s['hasil_pct'] == 10.0 and s['hasil_r'] == 2.0          # (110-100)/(100-95)


def test_kena_sl():
    s = rekam.evaluasi(sinyal(), harian([(101, 102, 99, 100), (99, 100, 94, 95)]))
    assert s['status'] == 'kena_sl' and s['harga_keluar'] == 95 and s['hasil_r'] == -1.0


def test_gap_turun_lewati_sl_dihitung_di_harga_buka():
    s = rekam.evaluasi(sinyal(), harian([(101, 102, 99, 100), (90, 92, 88, 89)]))
    assert s['status'] == 'kena_sl' and s['harga_keluar'] == 90 and s['hasil_r'] < -1


def test_sl_dan_tp_sama_hari_dianggap_sl_dulu():
    s = rekam.evaluasi(sinyal(), harian([(101, 120, 90, 100)]))
    assert s['status'] == 'kena_sl'


def test_gap_turun_di_bawah_zona_isi_di_harga_buka():
    s = rekam.evaluasi(sinyal(), harian([(97, 99, 96, 98)]))
    assert s['harga_masuk'] == 97 and s['status'] == 'terbuka'


def test_buka_di_bawah_sl_tidak_valid():
    s = rekam.evaluasi(sinyal(), harian([(90, 93, 88, 91)] + [(90, 91, 89, 90)] * 6))
    assert s['status'] == 'tidak_terisi' and s['harga_masuk'] is None


def test_tidak_terisi_setelah_lima_hari():
    s = rekam.evaluasi(sinyal(), harian([(105, 107, 103, 106)] * 5))
    assert s['status'] == 'tidak_terisi'


def test_masih_menunggu_sebelum_lima_hari():
    s = rekam.evaluasi(sinyal(), harian([(105, 107, 103, 106)] * 3))
    assert s['status'] == 'belum_masuk' and s['harga_terakhir'] == 106


def test_kedaluwarsa_trading_tujuh_hari():
    s = rekam.evaluasi(sinyal('Trading'), harian([(101, 103, 99, 101)] + [(101, 104, 99, 102)] * 6))
    assert s['status'] == 'kedaluwarsa' and s['harga_keluar'] == 102 and s['hasil_pct'] == 2.0


def test_terbuka_jika_belum_lewat_batas_tahan():
    s = rekam.evaluasi(sinyal('Swing'), harian([(101, 103, 99, 101)] + [(101, 104, 99, 102)] * 5))
    assert s['status'] == 'terbuka' and s['harga_terakhir'] == 102


def test_hari_sinyal_tidak_dihitung():
    # bar pada tanggal sinyal (2026-01-05) diabaikan walau menyentuh TP
    df = harian([(101, 120, 99, 118)], mulai='2026-01-05')
    s = rekam.evaluasi(sinyal(), df)
    assert s['status'] == 'belum_masuk' and s['harga_masuk'] is None


def test_status_final_tidak_berubah():
    s = rekam.evaluasi(sinyal(), harian([(101, 112, 99, 111)]))
    assert s['status'] == 'kena_tp'
    s2 = rekam.evaluasi(s, harian([(50, 51, 40, 45)]))
    assert s2 == s


def test_data_kosong_aman():
    s = sinyal()
    assert rekam.evaluasi(s, None) == s and rekam.evaluasi(s, pd.DataFrame()) == s


def test_statistik():
    daftar = []
    for status, pct, r, put in (('kena_tp', 10.0, 2.0, 'BELI'), ('kena_tp', 5.0, 1.0, 'BELI'), ('kena_sl', -5.0, -1.0, 'BELI'),
                                ('kena_sl', -5.0, -1.0, 'TUNGGU')):
        x = sinyal()
        x.update(status=status, hasil_pct=pct, hasil_r=r, putusan=put)
        daftar.append(x)
    t = sinyal(); t['status'] = 'tidak_terisi'; daftar.append(t)
    b = sinyal(); b['status'] = 'belum_masuk'; daftar.append(b)
    st = rekam.statistik(daftar)
    assert st['total'] == 6 and st['selesai'] == 4 and st['tidak_terisi'] == 1 and st['belum_masuk'] == 1
    assert st['semua']['win_rate'] == 50.0 and st['semua']['rata_r'] == 0.25
    assert st['per_putusan']['BELI']['n'] == 3 and st['per_putusan']['TUNGGU']['win_rate'] == 0.0
    assert st['sampel_kecil'] is True
    assert rekam.statistik([])['semua'] is None


def test_skor_evaluasi_dan_statistik():
    idx = pd.bdate_range('2026-01-06', periods=12)
    df = pd.DataFrame({'Close': [101 + i for i in range(12)]}, index=idx)           # hari pertama sesudah snapshot 101, naik 1 per hari
    b = rekam.evaluasi_skor(rekam.buat_skor('BBCA', 80, 'BULLISH', 100, tanggal='2026-01-05'), df)
    assert b['ret5'] == 5.0 and b['ret10'] == 10.0
    kurang = rekam.evaluasi_skor(rekam.buat_skor('BBCA', 80, 'BULLISH', 100, tanggal='2026-01-16'), df)
    assert kurang['ret5'] is None
    baris = [dict(b, id=str(i), skor=s, label=lab, ret5=r) for i, (s, lab, r) in enumerate(
        [(90, 'BULLISH', 4), (70, 'BULLISH', 2), (0, 'NETRAL', 0), (-60, 'BEARISH', -3), (-80, 'BEARISH', -5)] * 3)]
    st = rekam.statistik_skor(baris)
    assert st['per_label']['BULLISH']['rata_ret5'] == 3.0 and st['per_label']['BEARISH']['hit_pct'] == 0.0
    assert st['korelasi'] > 0.9 and st['sampel_kecil'] is True
    assert rekam.statistik_skor([]) is None


def test_pecah_download():
    idx = pd.bdate_range('2026-01-06', periods=3)
    kolom = pd.MultiIndex.from_product([['BBCA.JK', 'TLKM.JK'], ['Open', 'High', 'Low', 'Close']])
    df = pd.DataFrame(1.0, index=idx, columns=kolom)
    df[('TLKM.JK', 'Close')] = float('nan')
    hasil = rekam.pecah_download(df, ['BBCA', 'TLKM', 'XXXX'])
    assert set(hasil) == {'BBCA'}
