"""Rekam jejak sinyal: catat rekomendasi, evaluasi otomatis dengan data harian, hitung statistik.

Murni (tanpa Streamlit) supaya dipakai bersama oleh aplikasi dan tugas terjadwal (tugas/pantau.py).

Aturan evaluasi (sengaja konservatif):
- Dihitung mulai hari bursa BERIKUTNYA setelah sinyal dibuat.
- Masuk jika harga terendah hari itu menyentuh batas atas zona beli. Isi di batas atas zona; jika harga
  dibuka di bawahnya (gap turun), isi di harga buka. Jika isi sudah di bawah SL, sinyal dianggap tidak valid.
- Jika dalam satu hari SL dan TP sama-sama tersentuh, dianggap SL lebih dulu.
- Kena SL saat gap turun dihitung di harga buka (lebih buruk dari SL).
"""
import datetime as dt
import math

import pandas as pd

WIB = dt.timezone(dt.timedelta(hours=7))
FINAL = ('kena_tp', 'kena_sl', 'kedaluwarsa', 'tidak_terisi')
SELESAI_MASUK = ('kena_tp', 'kena_sl', 'kedaluwarsa')
AKTIF = ('belum_masuk', 'terbuka')
HARI_ISI = 5                                              # hari bursa menunggu harga masuk zona beli
HARI_TAHAN = {'Swing': 20, 'Trading': 7, 'Scalping': 3}   # hari bursa maksimal menahan posisi
SAMPEL_MIN = 30                                           # di bawah ini, statistik dianggap belum kuat
KOLOM_SINYAL = ['id', 'dibuat', 'tanggal', 'sumber', 'kode', 'gaya', 'putusan', 'keyakinan', 'beli_dari', 'beli_sampai',
                'tp', 'sl', 'rr', 'status', 'harga_masuk', 'tgl_masuk', 'harga_keluar', 'tgl_keluar', 'hasil_pct',
                'hasil_r', 'harga_terakhir', 'diperbarui']
KOLOM_SKOR = ['id', 'tanggal', 'kode', 'skor', 'label', 'harga', 'ret5', 'ret10']


def sekarang():
    return dt.datetime.now(WIB)


def hari_ini():
    return sekarang().date().isoformat()


def id_sinyal(kode, tanggal, sumber):
    return f'{kode}|{tanggal}|{sumber}'


def buat_sinyal(sumber, kode, level, gaya=None, putusan=None, keyakinan=None, rr=None, tanggal=None):
    """level: {beli_dari, beli_sampai, tp, sl}. Status awal: belum_masuk."""
    tanggal = tanggal or hari_ini()
    return {'id': id_sinyal(kode, tanggal, sumber), 'dibuat': sekarang().isoformat(timespec='seconds'), 'tanggal': tanggal,
            'sumber': sumber, 'kode': kode, 'gaya': gaya, 'putusan': putusan, 'keyakinan': keyakinan,
            'beli_dari': level['beli_dari'], 'beli_sampai': level['beli_sampai'], 'tp': level['tp'], 'sl': level['sl'],
            'rr': rr, 'status': 'belum_masuk', 'harga_masuk': None, 'tgl_masuk': None, 'harga_keluar': None,
            'tgl_keluar': None, 'hasil_pct': None, 'hasil_r': None, 'harga_terakhir': None,
            'diperbarui': sekarang().isoformat(timespec='seconds')}


def pecah_download(df, kodes):
    """Pecah hasil yf.download banyak saham (group_by='ticker', akhiran .JK) menjadi {kode: DataFrame}."""
    hasil = {}
    if df is None or len(df) == 0:
        return hasil
    for k in kodes:
        t = k + '.JK'
        if isinstance(df.columns, pd.MultiIndex):
            if t not in df.columns.get_level_values(0):
                continue
            d = df[t]
        else:
            d = df
        d = d.dropna(subset=['Close'])
        if len(d):
            hasil[k] = d.copy()
    return hasil


def _tanggal(v):
    return pd.Timestamp(v).date()


def _cek(o, h, l, sl, tp, hari_pertama):
    """Keluar karena SL/TP pada satu bar harian. SL diperiksa lebih dulu (konservatif)."""
    if not hari_pertama and o <= sl:
        return o, 'kena_sl'
    if l <= sl:
        return sl, 'kena_sl'
    if h >= tp:
        return tp, 'kena_tp'
    return None


def evaluasi(s, df):
    """Perbarui status satu sinyal dari data harian df (kolom Open/High/Low/Close). Hasil: salinan sinyal."""
    s = dict(s)
    if s.get('status') in FINAL or df is None or len(df) == 0:
        return s
    awal = _tanggal(s['tanggal'])
    bars = [(t.date(), float(r['Open']), float(r['High']), float(r['Low']), float(r['Close']))
            for t, r in df.iterrows() if t.date() > awal]
    if not bars:
        return s
    sl, tp, zona = float(s['sl']), float(s['tp']), float(s['beli_sampai'])
    tahan = HARI_TAHAN.get(s.get('gaya'), 7)
    masuk, hari_masuk, hari_isi, keluar = None, 0, 0, None
    for tgl, o, h, l, c in bars:
        if masuk is None:
            hari_isi += 1
            isi = (zona if o >= zona else o) if l <= zona else None
            if isi is not None and isi > sl:
                masuk, hari_masuk = isi, 1
                s['harga_masuk'], s['tgl_masuk'] = isi, tgl.isoformat()
                keluar = _cek(o, h, l, sl, tp, True)
            elif hari_isi >= HARI_ISI:
                s['status'] = 'tidak_terisi'
                break
        else:
            hari_masuk += 1
            keluar = _cek(o, h, l, sl, tp, False)
        if masuk is not None and keluar is None and hari_masuk >= tahan:
            keluar = (c, 'kedaluwarsa')
        if keluar:
            s['harga_keluar'], s['status'], s['tgl_keluar'] = keluar[0], keluar[1], tgl.isoformat()
            s['hasil_pct'] = round((keluar[0] / masuk - 1) * 100, 2)
            s['hasil_r'] = round((keluar[0] - masuk) / (masuk - sl), 2)
            break
    if s['status'] not in FINAL:
        s['status'] = 'terbuka' if masuk is not None else 'belum_masuk'
    s['harga_terakhir'] = bars[-1][4]
    s['diperbarui'] = sekarang().isoformat(timespec='seconds')
    return s


def _ringkas(daftar):
    n = len(daftar)
    if not n:
        return None
    menang = sum(1 for x in daftar if x['hasil_pct'] > 0)
    return {'n': n, 'win_rate': round(menang / n * 100, 1),
            'rata_r': round(sum(x['hasil_r'] for x in daftar) / n, 2),
            'rata_pct': round(sum(x['hasil_pct'] for x in daftar) / n, 2)}


def statistik(sinyal):
    """Ringkasan rekam jejak. Hanya sinyal yang sempat masuk dan sudah selesai yang masuk hitungan hasil."""
    selesai = [x for x in sinyal if x.get('status') in SELESAI_MASUK and x.get('hasil_pct') is not None]
    grup = lambda kunci: {g: _ringkas([x for x in selesai if (x.get(kunci) or '-') == g])
                          for g in sorted({(x.get(kunci) or '-') for x in selesai})}
    return {
        'total': len(sinyal), 'selesai': len(selesai),
        'belum_masuk': sum(1 for x in sinyal if x.get('status') == 'belum_masuk'),
        'terbuka': sum(1 for x in sinyal if x.get('status') == 'terbuka'),
        'tidak_terisi': sum(1 for x in sinyal if x.get('status') == 'tidak_terisi'),
        'semua': _ringkas(selesai), 'per_putusan': grup('putusan'), 'per_gaya': grup('gaya'),
        'sampel_kecil': len(selesai) < SAMPEL_MIN,
    }


# ---------- Validasi skor bullish (bola Terminal) ----------
def id_skor(kode, tanggal):
    return f'{kode}|{tanggal}'


def buat_skor(kode, skor, label, harga, tanggal=None):
    tanggal = tanggal or hari_ini()
    return {'id': id_skor(kode, tanggal), 'tanggal': tanggal, 'kode': kode, 'skor': int(skor), 'label': label,
            'harga': float(harga), 'ret5': None, 'ret10': None}


def _angka_harga(teks):
    """Harga dari tulisan Indonesia seperti '9.150' (titik ribuan) menjadi angka."""
    try:
        return float(str(teks).replace('.', '').replace(',', '.'))
    except ValueError:
        return float('nan')


def evaluasi_skor(baris, df):
    """Isi ret5/ret10 (persen) dari harga penutupan 5 dan 10 hari bursa setelah tanggal snapshot."""
    b = dict(baris)
    if df is None or len(df) == 0 or not b.get('harga'):
        return b
    awal = _tanggal(b['tanggal'])
    sesudah = [float(r['Close']) for t, r in df.iterrows() if t.date() > awal]
    for h, kunci in ((5, 'ret5'), (10, 'ret10')):
        if b.get(kunci) is None and len(sesudah) >= h:
            b[kunci] = round((sesudah[h - 1] / b['harga'] - 1) * 100, 2)
    return b


def statistik_skor(baris):
    """Rata-rata imbal 5 hari bursa per label skor, dan korelasi peringkat skor dengan imbal."""
    ada = [x for x in baris if x.get('ret5') is not None]
    if not ada:
        return None
    rata = sum(x['ret5'] for x in ada) / len(ada)
    per = {}
    for lab in ('BULLISH', 'NETRAL', 'BEARISH'):
        g = [x for x in ada if x.get('label') == lab]
        if g:
            per[lab] = {'n': len(g), 'rata_ret5': round(sum(x['ret5'] for x in g) / len(g), 2),
                        'hit_pct': round(sum(1 for x in g if x['ret5'] > 0) / len(g) * 100, 1)}
    df = pd.DataFrame(ada)
    kor = None
    if len(df) >= 10 and df['skor'].nunique() > 1:
        kor = df['skor'].rank().corr(df['ret5'].rank())
        kor = None if kor is None or math.isnan(kor) else round(float(kor), 3)
    return {'n': len(ada), 'rata_semua': round(rata, 2), 'per_label': per, 'korelasi': kor,
            'sampel_kecil': len(ada) < 100}
