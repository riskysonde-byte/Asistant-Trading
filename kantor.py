"""Logika kantor agen tanpa Streamlit, supaya mudah diuji.

Angka uang (lot, risiko, untung) selalu dihitung di sini oleh kode, bukan oleh AI.
"""
import json
import math
import re

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
def hitung_indikator(df):
    d = df.copy()
    d['MA20'] = d['Close'].rolling(20).mean()
    d['MA50'] = d['Close'].rolling(50).mean()
    d['VOL_MA20'] = d['Volume'].rolling(20).mean()
    delta = d['Close'].diff()
    naik = delta.clip(lower=0).rolling(14).mean()
    turun = (-delta.clip(upper=0)).rolling(14).mean()
    d['RSI14'] = 100 - 100 / (1 + naik / turun)
    ema12 = d['Close'].ewm(span=12).mean()
    ema26 = d['Close'].ewm(span=26).mean()
    d['MACD'] = ema12 - ema26
    d['MACD_SIGNAL'] = d['MACD'].ewm(span=9).mean()
    return d


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
def pagar(item, kas, pasar=None, riset=None):
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
    if putusan == 'BELI' and pasar == 'LIBUR':
        putusan = 'TUNGGU'
        catatan.append('Cek pasar pagi: LIBUR, hari ini tidak membuka posisi baru')
    if putusan == 'BELI' and riset == 'HINDARI':
        putusan = 'TUNGGU'
        catatan.append('Riset web menilai HINDARI')
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


# ---------- Cek pasar pagi / radar / riset ----------
def kode_valid(v):
    """Kode saham IDX 4 huruf kapital, atau None."""
    k = ''.join(c for c in str(v or '').upper() if c.isalnum())
    return k if len(k) == 4 and k.isalpha() else None


def kumpul_kode(*daftar, maks=30):
    """Kumpulkan kode unik dari beberapa daftar item ({'kode':..}) atau teks."""
    hasil = []
    for d in daftar:
        for x in d or []:
            k = kode_valid(x.get('kode') if isinstance(x, dict) else x)
            if k and k not in hasil:
                hasil.append(k)
    return hasil[:maks]


def bersihkan_pasar(r, jumlah_data):
    """Rapikan keputusan pasar dari AI dan terapkan pagar yang sama seperti aplikasi asli."""
    if not isinstance(r, dict):
        return None

    def daftar(a, n):
        return [str(x).strip() for x in a if str(x).strip()][:n] if isinstance(a, list) else []

    kd = str(r.get('kondisi', '')).upper()
    kd = 'RISK-OFF' if 'OFF' in kd else 'RISK-ON' if re.search(r'\bON\b|RISK-ON', kd) else 'NETRAL'
    kp = str(r.get('keputusan', '')).upper()
    kp = 'LIBUR' if ('LIBUR' in kp or 'TIDAK' in kp) else 'SELEKTIF' if 'SELEKTIF' in kp else 'TRADING'
    try:
        skor = max(0, min(100, int(round(float(r.get('skor'))))))
    except (TypeError, ValueError):
        skor = 50
    catatan = str(r.get('ringkas') or '')[:300]
    if jumlah_data < 2:
        if kp == 'TRADING':
            kp = 'SELEKTIF'
        catatan = (catatan + ' ' if catatan else '') + 'Data pasar yang terbaca sedikit, hasil kurang kuat.'
    if kd == 'RISK-OFF' and kp == 'TRADING':
        kp = 'SELEKTIF'
    if kd == 'RISK-ON' and kp == 'LIBUR' and skor >= 60:
        kp = 'SELEKTIF'
    gaya = []
    for g in daftar(r.get('gaya_cocok'), 3):
        n = 'Scalping' if re.search('scalp', g, re.I) else 'Trading' if re.search('trad', g, re.I) else 'Swing' if re.search('swing', g, re.I) else ''
        if n and n not in gaya:
            gaya.append(n)
    if kp == 'LIBUR':
        gaya = []
    try:
        uk = max(0, min(100, int(round(float(r.get('ukuran_posisi_pct')) / 25) * 25)))
    except (TypeError, ValueError):
        uk = 50 if kp == 'SELEKTIF' else 100
    if kp == 'LIBUR':
        uk = 0
    if kp == 'SELEKTIF' and uk > 50:
        uk = 50
    lv = r.get('level_ihsg')
    level = None
    if isinstance(lv, dict):
        def angka(a):
            out = []
            for v in (a if isinstance(a, list) else []):
                try:
                    out.append(float(v))
                except (TypeError, ValueError):
                    pass
            return out[:3]
        level = {'support': angka(lv.get('support')), 'resisten': angka(lv.get('resisten'))}
        if not (level['support'] or level['resisten']):
            level = None
    return {'keputusan': kp, 'kondisi': kd, 'skor': skor, 'gaya': gaya, 'ukuran': uk,
            'alasan': daftar(r.get('alasan'), 4), 'waspada': daftar(r.get('waspada'), 4),
            'level': level, 'ringkas': catatan}


# ---------- Sidang saham ----------
def bersihkan_sidang(res):
    """Rapikan naskah sidang dari AI. None jika tidak ada ronde."""
    if not isinstance(res, dict):
        return None
    ronde = []
    for x in (res.get('ronde') if isinstance(res.get('ronde'), list) else [])[:3]:
        if isinstance(x, dict) and (x.get('banteng') or x.get('beruang')):
            ronde.append({'banteng': str(x.get('banteng') or '-')[:360], 'beruang': str(x.get('beruang') or '-')[:360]})
    if not ronde:
        return None
    h = res.get('hakim') if isinstance(res.get('hakim'), dict) else {}
    pt = str(h.get('putusan', ''))
    put = 'BELI' if re.search('BELI', pt, re.I) else 'SKIP' if re.search('SKIP|HINDARI', pt, re.I) else 'TUNGGU'
    sk = res.get('skor') if isinstance(res.get('skor'), dict) else {}

    def nilai(v):
        try:
            return max(0.0, min(10.0, float(v)))
        except (TypeError, ValueError):
            return 5.0
    return {'ronde': ronde, 'putusan': put, 'alasan': str(h.get('alasan') or '')[:420],
            'syarat': str(h.get('syarat') or '')[:200], 'banteng': nilai(sk.get('banteng')), 'beruang': nilai(sk.get('beruang'))}
