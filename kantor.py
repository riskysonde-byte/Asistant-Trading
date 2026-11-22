"""Logika kantor agen tanpa Streamlit, supaya mudah diuji.

Angka uang (lot, risiko, untung) selalu dihitung di sini oleh kode, bukan oleh AI.
"""
import json
import math

import pandas as pd

MAKS_SAHAM = 30
GAYA = ['Swing', 'Trading', 'Scalping']
KOLOM_JURNAL = ['tanggal', 'kode', 'gaya', 'beli', 'jual', 'lot']
RR_MIN = 1.5


# ---------- Aturan IDX & money management ----------
def fraksi(h):
    if h < 200:
        return 1
    if h < 500:
        return 2
    if h < 2000:
        return 5
    if h < 5000:
        return 10
    return 25


def bulat_bawah(h):
    f = fraksi(h)
    return int(h // f * f)


def hitung_lot(modal, risiko_pct, entry, stop, porsi_maks_pct=25):
    lot_risiko = int(modal * risiko_pct / 100 / ((entry - stop) * 100))
    lot_porsi = int(modal * porsi_maks_pct / 100 / (entry * 100))
    return min(lot_risiko, lot_porsi), lot_risiko, lot_porsi


def atr(df, n=14):
    tr = pd.concat([
        df['High'] - df['Low'],
        (df['High'] - df['Close'].shift()).abs(),
        (df['Low'] - df['Close'].shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()


# ---------- Ringkasan data teknikal untuk agen ----------
def _angka(v, nd=2):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, nd)


def ringkas_saham(kode, d):
    """d: DataFrame berindikator (hasil hitung_indikator). Dipadatkan supaya muat untuk 30 saham."""
    a = d.iloc[-1]
    prev = float(d['Close'].iloc[-2]) if len(d) > 1 else float(a['Close'])
    ma200 = d['Close'].rolling(200).mean().iloc[-1] if len(d) >= 200 else None
    vol_ma = float(a['VOL_MA20']) if pd.notna(a['VOL_MA20']) else 0
    return {
        'kode': kode,
        'tanggal_bar': f'{d.index[-1]:%Y-%m-%d}',
        'harga': _angka(a['Close'], 0),
        'ubah_pct': _angka((float(a['Close']) / prev - 1) * 100) if prev else None,
        'ma20': _angka(a['MA20'], 0),
        'ma50': _angka(a['MA50'], 0),
        'ma200': _angka(ma200, 0),
        'rsi14': _angka(a['RSI14'], 1),
        'macd': _angka(a['MACD']),
        'macd_sinyal': _angka(a['MACD_SIGNAL']),
        'vol_x_rata20': _angka(float(a['Volume']) / vol_ma, 1) if vol_ma else None,
        'nilai_transaksi_miliar': _angka(float(a['Close']) * float(a['Volume']) / 1e9, 1),
        'atr14': _angka(atr(d).iloc[-1], 0),
        'low_20h': _angka(d['Low'].tail(20).min(), 0),
        'high_20h': _angka(d['High'].tail(20).max(), 0),
        'low_60h': _angka(d['Low'].tail(60).min(), 0),
        'high_60h': _angka(d['High'].tail(60).max(), 0),
    }


# ---------- Membaca jawaban agen ----------
def ambil_json(teks):
    """Ambil JSON (array atau objek) dari jawaban AI. None jika gagal."""
    if not teks:
        return None
    t = str(teks)
    posisi = [i for i in (t.find('['), t.find('{')) if i != -1]
    if not posisi:
        return None
    awal = min(posisi)
    akhir = t.rfind(']' if t[awal] == '[' else '}')
    if akhir <= awal:
        return None
    try:
        return json.loads(t[awal:akhir + 1])
    except ValueError:
        return None


def kumpul_daftar(daftar_teks, kunci='saham'):
    """Gabungkan jawaban beberapa potongan. Hasil: (daftar item dict, jumlah potongan gagal dibaca)."""
    item, gagal = [], 0
    for teks in daftar_teks:
        obj = ambil_json(teks)
        if isinstance(obj, dict) and isinstance(obj.get(kunci), list):
            obj = obj[kunci]
        if isinstance(obj, list):
            item.extend(x for x in obj if isinstance(x, dict))
        else:
            gagal += 1
    return item, gagal


def potong(daftar, ukuran):
    daftar = list(daftar)
    return [daftar[i:i + ukuran] for i in range(0, len(daftar), ukuran)]


def punya(v):
    """True jika v berisi data (bukan None, kosong, atau daftar/dict kosong)."""
    if v is None:
        return False
    if isinstance(v, (str, list, tuple, dict, set)):
        return len(v) > 0 and (not isinstance(v, str) or v.strip() != '')
    return True


def per_kode(item):
    return {str(x.get('kode', '')).strip().upper(): x for x in item if x.get('kode')}


# ---------- KASIR (dihitung kode) ----------
def level_valid(x):
    """Validasi level dari ANALIS dan bulatkan ke fraksi harga IDX. None jika tidak masuk akal."""
    try:
        dari = float(x['zona_beli_dari'])
        sampai = float(x['zona_beli_sampai'])
        tp = float(x['tp'])
        sl = float(x['sl'])
    except (KeyError, TypeError, ValueError):
        return None
    if dari > sampai:
        dari, sampai = sampai, dari
    if min(dari, sampai, tp, sl) <= 0:
        return None
    dari, sampai, tp, sl = bulat_bawah(dari), bulat_bawah(sampai), bulat_bawah(tp), bulat_bawah(sl)
    if not (sl < dari and tp > sampai):
        return None
    return {'beli_dari': dari, 'beli_sampai': sampai, 'tp': tp, 'sl': sl}


def kasir(level, modal, risiko_pct, porsi_pct=25):
    """Ukuran lot dan perkiraan untung/rugi dalam rupiah. Entry dihitung di batas atas zona beli (lebih hati-hati)."""
    if not level:
        return None
    entry, sl, tp = level['beli_sampai'], level['sl'], level['tp']
    lot, lot_r, lot_p = hitung_lot(modal, risiko_pct, entry, sl, porsi_pct)
    lot = max(lot, 0)
    return {
        'entry': entry, 'sl': sl, 'tp': tp,
        'lot': lot, 'lot_risiko': lot_r, 'lot_porsi': lot_p,
        'pembatas': 'risiko' if lot_r <= lot_p else 'porsi',
        'nilai': lot * 100 * entry,
        'risiko_rp': lot * 100 * (entry - sl),
        'untung_rp': lot * 100 * (tp - entry),
        'rr': round((tp - entry) / (entry - sl), 2),
        'catatan': '' if lot >= 1 else 'Modal tidak cukup untuk 1 lot dengan batas risiko ini',
    }


# ---------- Pagar keputusan KOORDINATOR ----------
def pagar(item, kas):
    """Keputusan AI tidak boleh BELI kalau hitungan kode tidak mendukung."""
    putusan = str((item or {}).get('putusan', '')).strip().upper()
    catatan = []
    if putusan not in ('BELI', 'TUNGGU', 'SKIP'):
        putusan = 'TUNGGU'
        catatan.append('Putusan KOORDINATOR tidak terbaca, diturunkan ke TUNGGU')
    if putusan == 'BELI':
        if not kas:
            putusan = 'TUNGGU'
            catatan.append('Level beli/TP/SL dari ANALIS tidak valid')
        elif kas['lot'] < 1:
            putusan = 'TUNGGU'
            catatan.append(kas['catatan'])
        elif kas['rr'] < RR_MIN:
            putusan = 'TUNGGU'
            catatan.append(f'RR {kas["rr"]} di bawah batas {RR_MIN}')
    try:
        yakin = int(round(float(item.get('keyakinan'))))
    except (AttributeError, TypeError, ValueError):
        yakin = 1
    return {
        'putusan': putusan,
        'keyakinan': min(10, max(1, yakin)),
        'alasan': str((item or {}).get('alasan', '')),
        'peringatan': str((item or {}).get('peringatan', '')),
        'catatan_sistem': '; '.join(catatan),
    }


# ---------- Jurnal untuk PELATIH ----------
def _ringkas_jurnal(g):
    menang = g[g['hasil_pct'] > 0]
    kalah = g[g['hasil_pct'] <= 0]
    return {
        'jumlah_trade': int(len(g)),
        'win_rate_pct': round(len(menang) / len(g) * 100, 1),
        'rata_hasil_pct': round(float(g['hasil_pct'].mean()), 2),
        'rata_menang_pct': round(float(menang['hasil_pct'].mean()), 2) if len(menang) else None,
        'rata_kalah_pct': round(float(kalah['hasil_pct'].mean()), 2) if len(kalah) else None,
        'total_rp': int(round(float(g['hasil_rp'].sum()))),
    }


def stat_jurnal(df):
    """Win rate dan rata-rata hasil per gaya, dihitung kode. None jika jurnal kosong."""
    if df is None or len(df) == 0 or any(k not in df.columns for k in ('kode', 'gaya', 'beli', 'jual', 'lot')):
        return None
    d = df.copy()
    for k in ('beli', 'jual', 'lot'):
        d[k] = pd.to_numeric(d[k], errors='coerce')
    d = d.dropna(subset=['beli', 'jual', 'lot'])
    d = d[d['beli'] > 0]
    if d.empty:
        return None
    d['gaya'] = d['gaya'].fillna('?').astype(str)
    d['hasil_pct'] = (d['jual'] / d['beli'] - 1) * 100
    d['hasil_rp'] = (d['jual'] - d['beli']) * d['lot'] * 100
    return {'total': _ringkas_jurnal(d),
            'per_gaya': {gaya: _ringkas_jurnal(g) for gaya, g in d.groupby('gaya')}}
