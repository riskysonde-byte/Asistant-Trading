"""Asisten Trading IDX: Scanner + Analisis satu saham (Streamlit)."""
import base64
import concurrent.futures as cf
import html
import json

import anthropic
import pandas as pd
import streamlit as st
import yfinance as yf

from agents import PROMPTS

st.set_page_config(page_title='Asisten Trading IDX', layout='wide')

MODEL = 'claude-sonnet-5-5'
STRATEGI = ['Swing Trading', 'Breakout', 'Volume Spike']
MIN_NILAI_TRANSAKSI = 5_000_000_000   # filter likuiditas: Rp5 miliar per hari

# Daftar emiten yang dipindai. Tambah sendiri: 'KODE': 'Nama Emiten'
EMITEN = {
    'BBCA': 'Bank Central Asia',
    'BBRI': 'Bank Rakyat Indonesia',
    'BMRI': 'Bank Mandiri',
    'TLKM': 'Telkom Indonesia',
    'ASII': 'Astra International',
    'ADRO': 'Alamtri Resources Indonesia',
    'ERAA': 'Erajaya Swasembada',
    'INET': 'Sinergi Inti Andalan Prima',
}


# ---------- Rahasia (API key & password) ----------
def rahasia(nama):
    try:
        return st.secrets[nama]
    except Exception:
        return None


sandi = rahasia('APP_PASSWORD')
if sandi:
    masukan = st.text_input('Password', type='password')
    if masukan != sandi:
        st.stop()


@st.cache_resource
def client():
    return anthropic.Anthropic(api_key=rahasia('ANTHROPIC_API_KEY'))


# ---------- Data ----------
@st.cache_data(ttl=300, show_spinner=False)
def get_ohlcv(kode, periode='1y'):
    # saham IDX di Yahoo Finance memakai akhiran .JK
    df = yf.download(kode + '.JK', period=periode, auto_adjust=False, progress=False)
    if df is None or df.empty:
        raise ValueError('Data ' + kode + ' tidak ditemukan')
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    return df


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


def get_broker_summary(kode):
    # Belum ada sumber data otomatis yang gratis. Nanti bisa diisi dari
    # CSV Stockbit: kolom broker, buy_val, sell_val. Sementara kosong.
    return None


@st.cache_data(ttl=900, show_spinner=False)
def get_fundamental(kode):
    # Data fundamental dari Yahoo Finance. Tidak selalu lengkap untuk saham IDX.
    try:
        info = yf.Ticker(kode + '.JK').info or {}
    except Exception:
        return None
    kunci = ['longName', 'sector', 'marketCap', 'trailingPE', 'priceToBook',
             'returnOnEquity', 'dividendYield', 'trailingEps', 'fiftyTwoWeekHigh', 'fiftyTwoWeekLow']
    hasil = {k: info.get(k) for k in kunci if info.get(k) is not None}
    return hasil or None


@st.cache_data(ttl=900, show_spinner=False)
def get_news(kode):
    # Judul berita dari Yahoo Finance. Struktur datanya bisa berubah, jadi dibungkus aman.
    try:
        items = yf.Ticker(kode + '.JK').news or []
    except Exception:
        return []
    hasil = []
    for it in items[:8]:
        c = it.get('content') if isinstance(it.get('content'), dict) else it
        judul = c.get('title') or it.get('title')
        if judul:
            hasil.append({'judul': judul, 'tanggal': str(c.get('pubDate') or it.get('providerPublishTime') or '')})
    return hasil


def hitung_lot(modal, risiko_pct, entry, stop, porsi_maks_pct=25):
    lot_risiko = int(modal * risiko_pct / 100 / ((entry - stop) * 100))
    lot_porsi = int(modal * porsi_maks_pct / 100 / (entry * 100))
    return min(lot_risiko, lot_porsi), lot_risiko, lot_porsi


# ---------- Hitungan scanner ----------
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


def atr(df, n=14):
    tr = pd.concat([
        df['High'] - df['Low'],
        (df['High'] - df['Close'].shift()).abs(),
        (df['Low'] - df['Close'].shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def umur_tren(d):
    hari = 0
    for ok in reversed((d['Close'] > d['MA20']).tolist()):
        if not ok:
            break
        hari += 1
    return hari


def deteksi(d):
    a, b = d.iloc[-1], d.iloc[-2]
    vol_x = float(a['Volume'] / a['VOL_MA20'])
    cocok = []
    if a['Close'] > a['MA20'] > a['MA50'] and 45 <= a['RSI14'] <= 65 and a['MACD'] > a['MACD_SIGNAL']:
        cocok.append('Swing Trading')
    if a['Close'] > d['High'].iloc[-21:-1].max() and vol_x >= 1.3:
        cocok.append('Breakout')
    if vol_x >= 2 and a['Close'] > b['Close']:
        cocok.append('Volume Spike')
    return cocok, vol_x


def info_broker(kode, bmap=None):
    # Prioritas: data hasil baca screenshot. Cadangan: get_broker_summary (kosong sementara).
    if bmap and bmap.get(kode, {}).get('broker'):
        return bmap[kode]['broker']
    data = get_broker_summary(kode)
    if data is None:
        return None
    beli = data[data['buy_val'] > data['sell_val']].copy()
    if beli.empty:
        return None
    beli['net'] = beli['buy_val'] - beli['sell_val']
    top = beli.sort_values('net', ascending=False).iloc[0]
    return {'kode': top['broker'], 'persen': round(float(top['net'] / beli['net'].sum() * 100), 1)}


@st.cache_data(ttl=900, show_spinner=False)
def pindai(universe, nama, bmap_json='{}'):
    bmap = json.loads(bmap_json)
    hasil = []
    for kode in universe:
        try:
            d = hitung_indikator(get_ohlcv(kode, '6mo'))
        except Exception:
            continue
        if len(d) < 60 or d['MA50'].isna().iloc[-1]:
            continue
        harga = float(d['Close'].iloc[-1])
        if harga * float(d['Volume'].iloc[-1]) < MIN_NILAI_TRANSAKSI:
            continue
        cocok, vol_x = deteksi(d)
        if not cocok:
            continue
        a = float(atr(d).iloc[-1])
        sl = bulat_bawah(harga - 1.5 * a)
        tp = bulat_bawah(harga + 3 * a)
        rr = (tp - harga) / (harga - sl) if harga > sl else 0
        broker = info_broker(kode, bmap)
        asing = bmap.get(kode, {}).get('asing')
        for s in cocok:
            hasil.append({
                'kode': kode, 'nama': nama.get(kode, kode), 'strategi': s,
                'harga': round(harga), 'tp': tp, 'sl': sl, 'rr': round(rr, 2),
                'vol_x': round(vol_x, 1), 'umur_tren': umur_tren(d),
                'broker': broker, 'asing_net': asing,
                'skor': round(min(100, 40 + 10 * vol_x + 10 * rr)),
            })
    return hasil


# ---------- Agen ----------
def blok_gambar(files):
    # Ubah screenshot yang diunggah menjadi blok gambar untuk Claude.
    blok = []
    for f in files or []:
        tipe = f.type if f.type in ('image/png', 'image/jpeg', 'image/webp', 'image/gif') else 'image/png'
        blok.append({'type': 'image', 'source': {
            'type': 'base64', 'media_type': tipe,
            'data': base64.b64encode(f.getvalue()).decode()}})
    return blok


def jalankan(nama, payload, max_tokens=1200, gambar=None):
    isi = list(gambar or [])
    isi.append({'type': 'text', 'text': json.dumps(payload, ensure_ascii=False, default=str)})
    r = client().messages.create(
        model=MODEL, max_tokens=max_tokens, system=PROMPTS[nama],
        messages=[{'role': 'user', 'content': isi}],
    )
    return r.content[0].text


def ekstrak_broker(files):
    # Baca screenshot broker summary / foreign flow. Persentase dihitung kode, bukan AI.
    if not files:
        return {}
    try:
        teks = jalankan('EKSTRAK', {'tugas': 'Baca semua screenshot terlampir.'}, max_tokens=2500, gambar=blok_gambar(files))
        arr = json.loads(teks[teks.index('['): teks.rindex(']') + 1])
    except Exception as e:
        st.warning('Screenshot gagal dibaca: ' + str(e)[:150])
        return {}
    hasil = {}
    for x in arr:
        kode = str(x.get('kode', '')).strip().upper()
        if not kode:
            continue
        beli = [b for b in (x.get('pembeli') or []) if isinstance(b, dict) and b.get('broker')
                and isinstance(b.get('net'), (int, float)) and b['net'] > 0]
        info = {}
        if beli:
            total = sum(b['net'] for b in beli)
            top = max(beli, key=lambda b: b['net'])
            info['broker'] = {'kode': str(top['broker']).upper(), 'persen': round(top['net'] / total * 100, 1)}
        if isinstance(x.get('asing_net'), (int, float)):
            info['asing'] = x['asing_net']
        if info:
            hasil[kode] = info
    return hasil


def paralel(tugas):
    # tugas: {nama_agen: (payload, gambar)}
    with cf.ThreadPoolExecutor() as ex:
        futures = {n: ex.submit(jalankan, n, p, 1200, g) for n, (p, g) in tugas.items()}
        return {n: f.result() for n, f in futures.items()}


def seleksi_llm(kandidat):
    try:
        teks = jalankan('SCANNER', kandidat, max_tokens=3500)
        hasil = json.loads(teks[teks.index('['): teks.rindex(']') + 1])
    except Exception as e:
        st.warning('Agen SCANNER gagal dipanggil, kartu memakai ringkasan otomatis. ' + str(e)[:150])
        return {}
    return {(x['kode'], x['strategi']): x for x in hasil}


def status_awal(umur):
    if umur <= 2:
        return 'Baru'
    if umur <= 10:
        return 'Early Trend'
    return 'Lanjutan'


def gabung(kandidat):
    llm = seleksi_llm(kandidat)
    akhir = []
    for k in kandidat:
        x = llm.get((k['kode'], k['strategi']))
        if llm and (x is None or not x.get('lolos', True)):
            continue
        k = dict(k)
        if x:
            k['status'] = x.get('status', status_awal(k['umur_tren']))
            k['skor'] = x.get('skor', k['skor'])
            k['ringkasan'] = x.get('ringkasan', '')
        else:
            k['status'] = status_awal(k['umur_tren'])
            k['ringkasan'] = 'Volume ' + str(k['vol_x']).replace('.', ',') + 'x rata-rata 20 hari, harga di atas MA20 selama ' + str(k['umur_tren']) + ' hari.'
        akhir.append(k)
    return akhir


# ---------- Kartu rekomendasi ----------
def rupiah(n):
    return f'{n:,.0f}'.replace(',', '.')


def persen(n):
    return f'{n:.1f}'.replace('.', ',')


def kartu_html(x):
    if x.get('broker'):
        broker = f'Broker {x["broker"]["kode"]} {persen(x["broker"]["persen"])}%'
    else:
        broker = 'Broker: data tidak tersedia'
    naik = (x['tp'] - x['harga']) / x['harga'] * 100
    turun = (x['harga'] - x['sl']) / x['harga'] * 100
    kotak = 'border-radius:6px;padding:8px 10px;'
    asing = x.get('asing_net')
    asing_txt = '' if asing is None else ' | Net asing ' + ('+' if asing > 0 else '') + rupiah(asing)
    label = 'font-size:10px;letter-spacing:.07em;opacity:.7;'
    return ''.join([
        '<div style="border:1px solid rgba(128,128,128,.35);border-radius:10px;padding:14px;margin-bottom:12px">',
        '<div style="display:flex;justify-content:space-between;align-items:flex-start">',
        f'<div><div style="font-size:20px;font-weight:700">{x["kode"]}</div>',
        f'<div style="font-size:12px;opacity:.7">{html.escape(x["nama"])}</div></div>',
        f'<span style="font-size:11px;padding:3px 9px;border-radius:99px;background:rgba(128,128,128,.22)">{html.escape(x["status"])}</span></div>',
        f'<div style="font-size:22px;font-weight:600;margin:6px 0">Rp{rupiah(x["harga"])}</div>',
        f'<span style="font-size:12px;padding:3px 9px;border-radius:4px;background:rgba(128,128,128,.22)">{broker}</span>',
        '<div style="display:flex;gap:8px;margin:10px 0">',
        f'<div style="flex:1;{kotak}background:rgba(31,164,99,.16)"><div style="{label}">TARGET (TP)</div>',
        f'<div style="color:#1fa463;font-weight:700">Rp{rupiah(x["tp"])} (+{persen(naik)}%)</div></div>',
        f'<div style="flex:1;{kotak}background:rgba(214,69,59,.16)"><div style="{label}">BATAS RUGI (SL)</div>',
        f'<div style="color:#d6453b;font-weight:700">Rp{rupiah(x["sl"])} (-{persen(turun)}%)</div></div></div>',
        f'<div style="font-size:12px;opacity:.7;margin-bottom:6px">RR {x["rr"]:.2f} | Volume {x["vol_x"]:.1f}x | Skor {x["skor"]}{asing_txt}</div>',
        f'<div style="font-size:13.5px">{html.escape(x["ringkasan"])}</div>',
        '</div>',
    ])


# ---------- Halaman ----------
def halaman_scanner():
    daftar = st.text_area('Kode saham yang dipindai (pisahkan koma)', ','.join(EMITEN))
    universe = tuple(k.strip().upper() for k in daftar.split(',') if k.strip())

    foto = st.file_uploader(
        'Screenshot broker summary / foreign flow dari Stockbit (opsional, bisa banyak saham)',
        type=['png', 'jpg', 'jpeg', 'webp'], accept_multiple_files=True, key='foto_scan')

    if st.button('Pindai bursa', key='btn_scan'):
        with st.spinner('Memindai saham...'):
            bmap = ekstrak_broker(foto)
            if foto:
                st.caption('Broker terbaca untuk: ' + (', '.join(bmap) if bmap else 'tidak ada saham yang terbaca'))
            mentah = pindai(universe, EMITEN, json.dumps(bmap))
            st.session_state['hasil'] = gabung(mentah) if mentah else []

    hasil = st.session_state.get('hasil')
    if hasil is None:
        st.info('Tekan Pindai bursa untuk mulai.')
        return
    if not hasil:
        st.info('Belum ada saham yang memenuhi syarat sinyal hari ini.')
        return

    c1, c2 = st.columns(2)
    urut = c1.selectbox('Urutkan', ['Skor', 'RR', 'Potensi naik'])
    rr_min = c2.slider('RR minimal', 0.0, 4.0, 1.5, 0.25)
    kunci = {
        'Skor': lambda x: x['skor'],
        'RR': lambda x: x['rr'],
        'Potensi naik': lambda x: x['tp'] / x['harga'],
    }[urut]

    jumlah = {s: sum(1 for x in hasil if x['strategi'] == s) for s in STRATEGI}
    tabs = st.tabs([f'{s} ({jumlah[s]})' for s in STRATEGI])
    for tab, s in zip(tabs, STRATEGI):
        with tab:
            kartu = sorted(
                [x for x in hasil if x['strategi'] == s and x['rr'] >= rr_min],
                key=kunci, reverse=True,
            )
            if not kartu:
                st.caption('Tidak ada saham yang lolos filter.')
            for i in range(0, len(kartu), 3):
                for kol, x in zip(st.columns(3), kartu[i:i + 3]):
                    kol.markdown(kartu_html(x), unsafe_allow_html=True)


def halaman_analisis():
    kode = st.text_input('Kode saham', 'BBCA').strip().upper()
    modal = st.number_input('Modal (Rp)', value=100_000_000, step=1_000_000)
    foto = st.file_uploader(
        'Screenshot broker summary / foreign flow dari Stockbit (opsional)',
        type=['png', 'jpg', 'jpeg', 'webp'], accept_multiple_files=True)
    if not st.button('Analisis', key='btn_analisis'):
        return

    try:
        d = hitung_indikator(get_ohlcv(kode))
    except Exception as e:
        st.error('Data saham gagal diambil: ' + str(e)[:150])
        return

    harga = float(d['Close'].iloc[-1])
    tgl = d.index[-1]
    st.caption(f'{kode}: Rp{rupiah(harga)} | data bar terakhir {tgl:%d-%m-%Y}. '
               'Sumber Yahoo Finance, bisa telat sekitar 10 menit dan tidak resmi.')

    ringkas = d.dropna().tail(60).round(2).to_dict('records')
    gambar = blok_gambar(foto)
    ada_foto = 'screenshot terlampir' if gambar else 'DATA TIDAK TERSEDIA'
    laporan = {}
    try:
        with st.spinner('Tim AI sedang bekerja, sekitar 1 menit...'):
            laporan.update(paralel({
                'ANALIS': ({'kode': kode, 'data': ringkas, 'fundamental': get_fundamental(kode)}, None),
                'PELOSI': ({'kode': kode, 'data': ada_foto}, gambar),
                'BROKER': ({'kode': kode, 'data': ada_foto}, gambar),
                'BERITA': ({'kode': kode, 'berita': get_news(kode)}, None),
            }))
            laporan['ENTRY'] = jalankan('ENTRY', {'analis': laporan['ANALIS'], 'broker': laporan['BROKER'], 'harga': harga})
            laporan['EXIT'] = jalankan('EXIT', {'analis': laporan['ANALIS'], 'entry': laporan['ENTRY']})
            laporan['RISIKO'] = jalankan('RISIKO', {'entry': laporan['ENTRY'], 'exit': laporan['EXIT']})
            laporan['BUDGET'] = jalankan('BUDGET', {'modal': modal, 'risiko': laporan['RISIKO'], 'entry': laporan['ENTRY']})
            laporan['ALERT'] = jalankan('ALERT', {k: laporan[k] for k in ['ENTRY', 'EXIT', 'RISIKO']})
            final = jalankan('ASISTEN / KOORDINATOR', laporan, max_tokens=1500)
    except Exception as e:
        st.error('Agen gagal berjalan. Cek ANTHROPIC_API_KEY di Secrets. ' + str(e)[:200])
        return

    st.session_state['analisis'] = {'kode': kode, 'harga': harga, 'final': final, 'laporan': laporan}


def tampil_analisis():
    a = st.session_state.get('analisis')
    if not a:
        return
    st.subheader('Keputusan ' + a['kode'])
    st.write(a['final'])

    st.markdown('**Kalkulator lot** (isi dari rencana di atas, hitungan pasti oleh kode)')
    modal = st.number_input('Modal (Rp)', value=100_000_000, step=1_000_000, key='k_modal')
    c1, c2 = st.columns(2)
    entry = c1.number_input('Harga beli', value=int(a['harga']), step=int(fraksi(a['harga'])), key='k_entry')
    stop = c2.number_input('Stop loss', value=bulat_bawah(a['harga'] * 0.97), step=int(fraksi(a['harga'])), key='k_stop')
    if stop < entry:
        lot, lot_r, lot_p = hitung_lot(modal, 1, entry, stop)
        st.write(f'**{lot} lot** = Rp{rupiah(lot * 100 * entry)} | risiko jika kena SL '
                 f'Rp{rupiah(lot * 100 * (entry - stop))} ({persen(lot * 100 * (entry - stop) / modal * 100)}% modal). '
                 f'Lot menurut risiko 1%: {lot_r}, menurut porsi 25%: {lot_p}.')
    else:
        st.warning('Stop loss harus di bawah harga beli.')

    for nama, isi in a['laporan'].items():
        with st.expander(nama):
            st.write(isi)


# ---------- Utama ----------
st.title('Asisten Trading IDX')
st.caption('Alat bantu analisis, bukan nasihat keuangan. Keputusan akhir ada di kamu.')
if not rahasia('ANTHROPIC_API_KEY'):
    st.warning('ANTHROPIC_API_KEY belum diisi di Secrets, jadi agen AI belum bisa dipakai.')

tab_scan, tab_analisis = st.tabs(['Scanner', 'Analisis satu saham'])
with tab_scan:
    halaman_scanner()
with tab_analisis:
    halaman_analisis()
    tampil_analisis()
