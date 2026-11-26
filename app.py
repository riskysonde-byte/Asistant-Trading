"""Asisten Trading IDX: Scanner + Analisis satu saham (Streamlit)."""
import concurrent.futures as cf
import html
import json

import pandas as pd
import streamlit as st
import yfinance as yf

import grafik
import live
import tema
from jejak import catat
from tim_agen import TIM
from arena import halaman_arena, halaman_tanya
from terminal import halaman_terminal
from fitur_web import get_pasar_dunia, halaman_pasar, halaman_riset, pasar_hari_ini, riset_terbaru
from gemini import blok_gambar, jalankan, kunci, rahasia
from kantor import (GAYA, hitung_indikator, KOLOM_JURNAL, MAKS_SAHAM, ambil_json, atr, bulat_bawah, fraksi, hitung_lot,
                    kasir, kumpul_daftar, level_valid, pagar, per_kode, potong, punya, ringkas_saham,
                    stat_jurnal)

st.set_page_config(page_title='Asisten Trading IDX', page_icon='📈', layout='wide')

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
sandi = rahasia('APP_PASSWORD')
if sandi:
    masukan = st.text_input('Password', type='password')
    if masukan != sandi:
        st.stop()


# ---------- Data ----------
@st.cache_data(ttl=300, show_spinner=False)
def get_ohlcv(kode, periode='1y'):
    # saham IDX di Yahoo Finance memakai akhiran .JK
    df = yf.download(kode + '.JK', period=periode, auto_adjust=False, progress=False)
    if df is None or df.empty:
        raise ValueError('Data ' + kode + ' tidak ditemukan')
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    return df


def get_ohlcv_live(kode, periode='1y', data_live=None):
    """Data harian + bar hari ini diperbarui dari data per menit (kalau tersedia)."""
    df = get_ohlcv(kode, periode)
    if data_live is None:
        data_live = live.harga_live((kode,))
    return live.sambung_live(df, data_live.get(kode))


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


# ---------- Hitungan scanner ----------
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


@st.cache_data(ttl=60, show_spinner=False)
def pindai(universe, nama, bmap_json='{}'):
    bmap = json.loads(bmap_json)
    data_live = live.harga_live(universe)   # satu permintaan untuk semua saham
    hasil = []
    for kode in universe:
        try:
            d = hitung_indikator(get_ohlcv_live(kode, '6mo', data_live))
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
        data_live = live.harga_live((kode,))
        d = hitung_indikator(get_ohlcv_live(kode, '1y', data_live))
    except Exception as e:
        st.error('Data saham gagal diambil: ' + str(e)[:150])
        return

    harga = float(d['Close'].iloc[-1])
    tgl = d.index[-1]
    lv = data_live.get(kode)
    if lv:
        st.caption(f'{kode}: Rp{rupiah(harga)} ({lv["ubah_pct"]:+.2f}%) | update {lv["waktu"]:%d-%m-%Y %H:%M} WIB. '
                   'Sumber Yahoo Finance, tertunda sekitar 10-15 menit dan tidak resmi.')
    else:
        st.caption(f'{kode}: Rp{rupiah(harga)} | data bar terakhir {tgl:%d-%m-%Y}. '
                   'Data per menit tidak tersedia; sumber Yahoo Finance, tidak resmi.')

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
        st.error('Agen gagal berjalan. Cek GEMINI_API_KEY di Secrets. ' + str(e)[:200])
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


def tabel_live(data):
    baris = []
    for k, x in data.items():
        baris.append({
            'Kode': k, 'Nama': EMITEN.get(k, ''), 'Harga': x['harga'],
            'Ubah': x['ubah'], 'Ubah %': x['ubah_pct'], 'Open': x['open'],
            'High': x['high'], 'Low': x['low'], 'Volume (lot)': x['volume'] / 100,
            'Update': x['waktu'].strftime('%H:%M'),
        })
    df = pd.DataFrame(baris).sort_values('Ubah %', ascending=False)

    def warna(v):
        if v > 0:
            return 'color: #16a34a'
        if v < 0:
            return 'color: #dc2626'
        return ''

    return df.style.map(warna, subset=['Ubah', 'Ubah %']).format({
        'Harga': rupiah, 'Ubah': lambda v: f'{v:+,.0f}'.replace(',', '.'),
        'Ubah %': '{:+.2f}%', 'Open': rupiah, 'High': rupiah, 'Low': rupiah,
        'Volume (lot)': rupiah,
    })


def halaman_live():
    with st.expander('⚙️ Atur watchlist dan refresh'):
        daftar = st.text_area('Watchlist (pisahkan koma)', ','.join(EMITEN), key='watchlist')
        c1, c2 = st.columns(2)
        otomatis = c1.toggle('Refresh otomatis', value=True)
        detik = c2.selectbox('Setiap', [15, 30, 60, 120], index=1, format_func=lambda s: f'{s} detik')
    kodes = tuple(dict.fromkeys(k.strip().upper() for k in daftar.split(',') if k.strip()))

    def panel():
        st.caption(f'Diperbarui {live.sekarang():%H:%M:%S} WIB')
        data = live.harga_live(kodes)
        if not data:
            st.warning('Data per menit belum bisa diambil. Coba lagi sebentar.')
            return
        gagal = [k for k in kodes if k not in data]
        if gagal:
            st.caption('Tidak ada data untuk: ' + ', '.join(gagal))
        pilih = st.session_state.get('live_pil') or next(iter(data))
        if pilih not in data:
            pilih = next(iter(data))
        tema.watchlist(data, EMITEN, pilih)
        with st.expander('Detail tabel (Open, High, Low, Volume)'):
            st.dataframe(tabel_live(data), hide_index=True, width='stretch')
        pilih = st.pills('Pilih saham untuk grafik', list(data), selection_mode='single', default=next(iter(data)), key='live_pil') or pilih
        x = data[pilih]
        tema.statistik(pilih, x)

        g1, g2, g3 = st.columns(3)
        mode = g1.segmented_control('Tampilan', ['Intraday', 'Harian'], default='Intraday', key='grafik_mode')
        if mode == 'Harian':
            try:
                df = live.sambung_live(live.get_harian_banyak((pilih,), '1y')[pilih], x)
                fig = grafik.candle(df, pilih, intraday=False, ma=(20, 50), kunci_ui=pilih + 'H', tampil_n=130)
            except Exception:
                st.info('Data harian belum bisa diambil.')
                return
        else:
            menit = g2.segmented_control('Interval', [1, 5, 15], default=5, format_func=lambda m: f'{m} mnt', key='grafik_tf') or 5
            rentang = g3.segmented_control('Rentang', ['Hari ini', '5 hari'], default='Hari ini', key='grafik_rentang') or 'Hari ini'
            bar = live.get_intraday(kodes).get(pilih)
            if bar is None:
                st.info('Data per menit belum tersedia.')
                return
            mulai = bar.index[bar.index.date == x['tanggal']][0].tz_localize(None) if rentang == 'Hari ini' else None
            fig = grafik.candle(grafik.resample_ohlcv(bar, menit), pilih, prev_close=x['prev'], mulai=mulai,
                                kunci_ui=f'{pilih}-{menit}-{rentang}')
        st.plotly_chart(fig, width='stretch', config=grafik.CONFIG, key='grafik_live')

    st.fragment(run_every=detik if otomatis else None)(panel)()


# ---------- Kantor agen (10 anggota tim) ----------
@st.cache_data(ttl=3600, show_spinner=False)
def get_kalender(kode):
    try:
        cal = yf.Ticker(kode + '.JK').calendar
    except Exception:
        return None
    if not isinstance(cal, dict) or not cal:
        return None
    return {str(k): ', '.join(str(x)[:10] for x in v) if isinstance(v, (list, tuple)) else str(v)[:30]
            for k, v in cal.items()}


@st.cache_data(ttl=300, show_spinner=False)
def get_makro():
    try:
        df = yf.download(['^JKSE', 'USDIDR=X'], period='7d', auto_adjust=False, progress=False, group_by='ticker')
    except Exception:
        return None
    hasil = {}
    for nama, t in (('IHSG', '^JKSE'), ('USDIDR', 'USDIDR=X')):
        try:
            c = df[t]['Close'].dropna()
            hasil[nama] = {'terakhir': round(float(c.iloc[-1]), 2),
                           'ubah_1_hari_pct': round(float(c.iloc[-1] / c.iloc[-2] - 1) * 100, 2),
                           'ubah_periode_pct': round(float(c.iloc[-1] / c.iloc[0] - 1) * 100, 2)}
        except Exception:
            continue
    return hasil or None


def kumpulkan_data(kodes, auto_fund):
    """Teknikal (harga terkini) + fundamental/berita/kalender otomatis. Hasil: teknikal, ekstra, gagal."""
    harian = live.get_harian_banyak(tuple(kodes), '1y')
    data_live = live.harga_live(kodes)
    teknikal, gagal = {}, []
    for k in kodes:
        try:
            d = hitung_indikator(live.sambung_live(harian[k], data_live.get(k)))
            if len(d) < 60 or d['MA50'].isna().iloc[-1]:
                raise ValueError('data kurang')
            teknikal[k] = ringkas_saham(k, d)
        except Exception:
            gagal.append(k)
    ekstra = {k: {} for k in teknikal}
    if auto_fund and teknikal:
        def ambil(k):
            return k, get_fundamental(k), get_news(k), get_kalender(k)
        with cf.ThreadPoolExecutor(max_workers=6) as ex:
            for k, f, n, c in ex.map(ambil, list(teknikal)):
                ekstra[k] = {'fundamental': f, 'berita': n, 'kalender': c}
    return teknikal, ekstra, gagal


def paralel_aman(panggilan, maks=4):
    """panggilan: {kunci: (agen, payload, token, gambar)} -> {kunci: teks atau Exception}. Satu gagal tidak menghentikan yang lain."""
    def satu(v):
        agen, payload, token, gambar = v
        try:
            return jalankan(agen, payload, token, gambar)
        except Exception as e:
            return e
    with cf.ThreadPoolExecutor(max_workers=maks) as ex:
        futs = {k: ex.submit(satu, v) for k, v in panggilan.items()}
        return {k: f.result() for k, f in futs.items()}


def jalankan_kantor(kodes, modal, risiko, foto, teks_user, auto_fund, status):
    hasil = {'waktu': live.sekarang(), 'dilewati': {}, 'galat': {}, 'modal': modal, 'risiko': risiko}
    catat('KANTOR', f'Mulai: {len(kodes)} saham dipantau')

    status.write('Mengambil data harga terkini...')
    teknikal, ekstra, gagal = kumpulkan_data(kodes, auto_fund)
    hasil['gagal_data'] = gagal
    catat('DATA', f'{len(teknikal)} saham dengan harga terkini' + (f', gagal: {", ".join(gagal)}' if gagal else ''),
          'warn' if gagal else 'info')
    if not teknikal:
        raise ValueError('Tidak ada saham yang datanya bisa diambil')

    # 1. PEMBURU: baca screenshot dan teks
    fakta, makro_unggahan = {}, None
    gambar = blok_gambar(foto)
    if gambar or teks_user.strip():
        status.write('PEMBURU membaca screenshot dan teks...')
        try:
            teks = jalankan('TIM_PEMBURU', {'kode_dipantau': list(teknikal), 'teks_pengguna': teks_user or None,
                                            'screenshot': 'terlampir' if gambar else 'tidak ada'}, 8000, gambar)
            obj = ambil_json(teks)
            if isinstance(obj, dict):
                fakta = per_kode(obj.get('saham') or [])
                makro_unggahan = obj.get('makro')
            elif isinstance(obj, list):
                fakta = per_kode(obj)
            else:
                hasil['galat']['PEMBURU'] = 'Jawaban tidak terbaca sebagai JSON'
        except Exception as e:
            hasil['galat']['PEMBURU'] = str(e)[:150]
    else:
        hasil['dilewati']['PEMBURU'] = 'tidak ada screenshot atau teks yang diunggah'

    # 2. Paket data per saham
    paket = {}
    for k, tk in teknikal.items():
        f, e = fakta.get(k, {}), ekstra.get(k, {})
        paket[k] = {
            'teknikal': tk,
            'broker_asing': {x: f[x] for x in ('broker', 'asing_net') if punya(f.get(x))},
            'berita': list(e.get('berita') or []) + list(f.get('berita') or []),
            'fundamental': {**(e.get('fundamental') or {}), **{x: f[x] for x in ('per', 'pbv', 'roe') if punya(f.get(x))}},
            'jadwal': {**({'kalender_yahoo': e['kalender']} if punya(e.get('kalender')) else {}),
                       **({'dari_unggahan': f['jadwal']} if punya(f.get('jadwal')) else {})},
        }

    # 3. Agen paralel
    status.write('Tim menganalisis ' + str(len(paket)) + ' saham...')
    panggilan = {}
    for i, grup in enumerate(potong(paket, 8)):
        panggilan[('TIM_ANALIS', i)] = ('TIM_ANALIS', {
            'catatan': 'Harga Yahoo tertunda sekitar 10-15 menit.',
            'saham': [paket[k]['teknikal'] for k in grup]}, 8000, None)
    sumber = {'TIM_PENCIUM': 'broker_asing', 'TIM_WARTAWAN': 'berita', 'TIM_DOKTER': 'fundamental', 'TIM_KALENDER': 'jadwal'}
    for agen, kunci_data in sumber.items():
        ada = [k for k in paket if punya(paket[k][kunci_data])]
        if not ada:
            hasil['dilewati'][agen[4:]] = 'tidak ada data'
            continue
        for i, grup in enumerate(potong(ada, 10)):
            panggilan[(agen, i)] = (agen, {'saham': [
                {'kode': k, 'harga': paket[k]['teknikal']['harga'], kunci_data: paket[k][kunci_data]} for k in grup]}, 6000, None)
    data_makro = {'otomatis': get_makro(), 'dari_unggahan': makro_unggahan}
    if punya(data_makro['otomatis']) or punya(data_makro['dari_unggahan']):
        panggilan[('TIM_MAKRO', 0)] = ('TIM_MAKRO', data_makro, 3000, None)
    else:
        hasil['dilewati']['MAKRO'] = 'tidak ada data'
    jawaban = paralel_aman(panggilan)

    lap = {k: {} for k in paket}
    makro_teks = None
    for agen in ('TIM_ANALIS', 'TIM_PENCIUM', 'TIM_WARTAWAN', 'TIM_DOKTER', 'TIM_KALENDER', 'TIM_MAKRO'):
        potongan = [v for (a, _), v in sorted(jawaban.items(), key=lambda x: x[0][1]) if a == agen]
        if not potongan:
            continue
        galat = [v for v in potongan if isinstance(v, Exception)]
        teks_ok = [v for v in potongan if not isinstance(v, Exception)]
        if galat:
            hasil['galat'][agen[4:]] = str(galat[0])[:150]
        if agen == 'TIM_MAKRO':
            makro_teks = ambil_json(teks_ok[0]) if teks_ok else None
            if teks_ok and makro_teks is None:
                makro_teks = {'ringkas': teks_ok[0][:500]}
            continue
        item, gagal_baca = kumpul_daftar(teks_ok)
        if gagal_baca:
            hasil['galat'][agen[4:]] = hasil['galat'].get(agen[4:], '') + f' {gagal_baca} bagian jawaban tidak terbaca'
        for kode, x in per_kode(item).items():
            if kode in lap:
                lap[kode][agen[4:]] = x

    # 4. KASIR (hitungan kode)
    status.write('KASIR menghitung lot dan risiko...')
    pasar = pasar_hari_ini()
    risiko_ef = risiko * pasar['ukuran'] / 100 if pasar and pasar['ukuran'] > 0 else risiko
    hasil['pasar'] = {k: pasar[k] for k in ('keputusan', 'kondisi', 'skor', 'ukuran')} if pasar else None
    hasil['risiko_efektif'] = round(risiko_ef, 2)
    kas = {k: kasir(level_valid(lap[k].get('ANALIS') or {}), modal, risiko_ef) for k in paket}
    riset = riset_terbaru()

    # 5. KOORDINATOR
    status.write('KOORDINATOR menyusun putusan akhir...')
    kunci_lap = ('ANALIS', 'PENCIUM', 'WARTAWAN', 'DOKTER', 'KALENDER')
    panggilan = {('TIM_KOORDINATOR', i): ('TIM_KOORDINATOR', {
        'saham': [{'kode': k, 'harga': paket[k]['teknikal']['harga'],
                   **{n: lap[k][n] for n in kunci_lap if n in lap[k]}, 'KASIR': kas[k],
                   **({'RISET_WEB': {x: riset[k]['r'].get(x) for x in ('putusan_web', 'ringkas', 'poin_minus')}} if k in riset else {})}
                  for k in grup],
        'MAKRO': makro_teks, 'agen_dilewati': list(hasil['dilewati']), 'CEK_PASAR': hasil['pasar']}, 6000, None)
        for i, grup in enumerate(potong(paket, 10))}
    jawaban = paralel_aman(panggilan)
    teks_ok = [v for v in jawaban.values() if not isinstance(v, Exception)]
    if len(teks_ok) < len(jawaban):
        hasil['galat']['KOORDINATOR'] = str([v for v in jawaban.values() if isinstance(v, Exception)][0])[:150]
    putusan_ai = per_kode(kumpul_daftar(teks_ok)[0])

    catat('KASIR', f'{sum(1 for v in kas.values() if v)} rencana lot dan risiko dihitung')
    hasil['makro'] = makro_teks
    hasil['saham'] = {k: {'teknikal': paket[k]['teknikal'], 'lap': lap[k], 'kasir': kas[k],
                          'putusan': pagar(putusan_ai.get(k), kas[k], pasar['keputusan'] if pasar else None,
                                           str(riset[k]['r'].get('putusan_web', '')).upper() if k in riset else None)}
                          for k in paket}
    for agen, ket in hasil['dilewati'].items():
        catat(agen, f'dilewati: {ket}', 'warn')
    for agen, ket in hasil['galat'].items():
        catat(agen, f'bermasalah: {ket}', 'err')
    hitung = {p: sum(1 for x in hasil['saham'].values() if x['putusan']['putusan'] == p) for p in ('BELI', 'TUNGGU', 'SKIP')}
    catat('KOORDINATOR', f'BELI {hitung["BELI"]} · TUNGGU {hitung["TUNGGU"]} · SKIP {hitung["SKIP"]}', 'ok')
    return hasil


def md_laporan(x):
    if isinstance(x, dict):
        return '\n'.join(f'- **{k}**: {md_laporan(v)}' if not isinstance(v, (dict, list)) else f'- **{k}**:\n{md_laporan(v)}'
                         for k, v in x.items() if k != 'kode')
    if isinstance(x, list):
        return '\n'.join('  ' + (md_laporan(i) if not isinstance(i, dict) else md_laporan(i).replace('\n', '\n  '))
                         for i in x)
    return str(x)


IKON = {'BELI': '🟢', 'TUNGGU': '🟡', 'SKIP': '🔴'}


def tampil_kantor():
    h = st.session_state.get('kantor')
    if not h:
        return
    st.caption(f'Hasil {h["waktu"]:%d-%m-%Y %H:%M} WIB | modal Rp{rupiah(h["modal"])} | risiko {h["risiko"]}% per trade. '
               'Harga Yahoo tertunda sekitar 10-15 menit.')
    if h.get('pasar'):
        ps = h['pasar']
        st.info(f'Cek pasar hari ini: {ps["keputusan"]} ({ps["kondisi"]}, skor {ps["skor"]}). '
                f'Ukuran posisi {ps["ukuran"]}%, jadi risiko per trade dipakai {h["risiko_efektif"]}%.')
    else:
        st.caption('Belum ada Cek pasar hari ini (tab Pasar). Ukuran posisi memakai risiko penuh.')
    if h['gagal_data']:
        st.warning('Data tidak bisa diambil untuk: ' + ', '.join(h['gagal_data']))
    for agen, ket in h['dilewati'].items():
        st.caption(f'⏭️ {agen} dilewati: {ket}')
    for agen, ket in h['galat'].items():
        st.warning(f'{agen} bermasalah: {ket}')

    urutan = sorted(h['saham'].items(), key=lambda kv: (['BELI', 'TUNGGU', 'SKIP'].index(kv[1]['putusan']['putusan']),
                                                        -kv[1]['putusan']['keyakinan']))
    baris = []
    for k, x in urutan:
        a, ks, p = x['lap'].get('ANALIS') or {}, x['kasir'], x['putusan']
        baris.append({
            'Kode': k, 'Putusan': IKON[p['putusan']] + ' ' + p['putusan'], 'Yakin': f'{p["keyakinan"]}/10',
            'Gaya': a.get('gaya') or '-', 'Harga': rupiah(x['teknikal']['harga']),
            'Zona beli': rupiah(ks['entry']) if ks else '-', 'TP': rupiah(ks['tp']) if ks else '-',
            'SL': rupiah(ks['sl']) if ks else '-', 'RR': str(ks['rr']) if ks else '-', 'Lot': str(ks['lot']) if ks else '-',
            'Nilai (Rp)': rupiah(ks['nilai']) if ks else '-', 'Risiko (Rp)': rupiah(ks['risiko_rp']) if ks else '-',
        })
    st.dataframe(pd.DataFrame(baris), hide_index=True, width='stretch')

    if h.get('makro'):
        with st.expander('MAKRO: kondisi pasar'):
            st.markdown(md_laporan(h['makro']))
    for k, x in urutan:
        p, ks = x['putusan'], x['kasir']
        with st.expander(f'{IKON[p["putusan"]]} {k}: {p["putusan"]} ({p["keyakinan"]}/10)'):
            if p['alasan']:
                st.write(p['alasan'])
            if p['peringatan']:
                st.warning(p['peringatan'])
            if p['catatan_sistem']:
                st.caption('Catatan sistem: ' + p['catatan_sistem'])
            if ks:
                st.markdown(f'**KASIR** (dihitung kode): zona beli sampai Rp{rupiah(ks["entry"])}, SL Rp{rupiah(ks["sl"])}, '
                            f'TP Rp{rupiah(ks["tp"])}, RR {ks["rr"]}. **{ks["lot"]} lot** = Rp{rupiah(ks["nilai"])}; '
                            f'rugi jika kena SL Rp{rupiah(ks["risiko_rp"])}, untung jika kena TP Rp{rupiah(ks["untung_rp"])}. '
                            f'Pembatas lot: {ks["pembatas"]}.')
            for nama, isi in x['lap'].items():
                st.markdown(f'**{nama}**')
                st.markdown(md_laporan(isi))


def halaman_jurnal():
    if 'jurnal' not in st.session_state:
        st.session_state['jurnal'] = pd.DataFrame(columns=KOLOM_JURNAL)
    st.caption('Catat trade yang sudah selesai. Streamlit tidak menyimpan data permanen, jadi unduh CSV-nya '
               'dan muat lagi lain kali.')
    up = st.file_uploader('Muat jurnal (CSV)', type=['csv'], key='jurnal_csv')
    if up is not None and st.session_state.get('jurnal_token') != (up.name, up.size):
        try:
            muat = pd.read_csv(up)
            st.session_state['jurnal'] = muat.reindex(columns=KOLOM_JURNAL)
            st.session_state['jurnal_token'] = (up.name, up.size)
        except Exception as e:
            st.error('CSV tidak terbaca: ' + str(e)[:120])
    with st.form('jurnal_form', clear_on_submit=True):
        c = st.columns(5)
        kode = c[0].text_input('Kode')
        gaya = c[1].selectbox('Gaya', GAYA)
        beli = c[2].number_input('Harga beli', min_value=0, step=1)
        jual = c[3].number_input('Harga jual', min_value=0, step=1)
        lot = c[4].number_input('Lot', min_value=0, step=1)
        if st.form_submit_button('Tambah ke jurnal'):
            if kode.strip() and beli > 0 and lot > 0:
                baru = pd.DataFrame([{'tanggal': live.sekarang().strftime('%Y-%m-%d'), 'kode': kode.strip().upper(),
                                      'gaya': gaya, 'beli': beli, 'jual': jual, 'lot': lot}])
                st.session_state['jurnal'] = pd.concat([st.session_state['jurnal'], baru], ignore_index=True)
            else:
                st.warning('Isi kode, harga beli, dan lot.')
    jurnal = st.session_state['jurnal']
    stat = stat_jurnal(jurnal)
    if stat is None:
        st.info('Jurnal masih kosong.')
        return
    st.dataframe(jurnal, hide_index=True, width='stretch')
    st.download_button('Unduh jurnal (CSV)', jurnal.to_csv(index=False), 'jurnal_trading.csv', 'text/csv')
    t = stat['total']
    m1, m2, m3 = st.columns(3)
    m1.metric('Win rate', f'{t["win_rate_pct"]}%', f'{t["jumlah_trade"]} trade')
    m2.metric('Rata-rata hasil', f'{t["rata_hasil_pct"]}%')
    m3.metric('Total', 'Rp' + rupiah(t['total_rp']))
    st.dataframe(pd.DataFrame(stat['per_gaya']).T, width='stretch')
    if st.button('Minta PELATIH mengulas', key='btn_pelatih'):
        try:
            with st.spinner('PELATIH membaca jurnalmu...'):
                st.session_state['pelatih'] = jalankan('TIM_PELATIH', {
                    'statistik': stat, 'trade_terakhir': jurnal.tail(30).to_dict('records')}, 3000)
        except Exception as e:
            st.error('PELATIH gagal: ' + str(e)[:200])
    if st.session_state.get('pelatih'):
        st.markdown(st.session_state['pelatih'])


def halaman_kantor():
    with st.expander('Anggota tim (10 agen)'):
        for nama, tugas in TIM:
            st.markdown(f'**{nama}**: {tugas}')

    daftar = st.text_area('Saham yang dipantau (pisahkan koma, maksimal ' + str(MAKS_SAHAM) + ')',
                          ','.join(EMITEN), key='kantor_daftar')
    kodes = list(dict.fromkeys(k.strip().upper() for k in daftar.split(',') if k.strip()))
    if len(kodes) > MAKS_SAHAM:
        st.warning(f'Hanya {MAKS_SAHAM} saham pertama yang dipakai.')
        kodes = kodes[:MAKS_SAHAM]
    c1, c2 = st.columns(2)
    modal = c1.number_input('Modal (Rp)', value=100_000_000, step=1_000_000, key='kantor_modal')
    risiko = c2.number_input('Batas risiko per trade (% modal)', value=1.0, min_value=0.1, max_value=5.0, step=0.1)
    foto = st.file_uploader('Screenshot (broker summary, berita, fundamental, makro, jadwal). Opsional, banyak sekaligus',
                            type=['png', 'jpg', 'jpeg', 'webp'], accept_multiple_files=True, key='kantor_foto')
    teks_user = st.text_area('Teks tambahan (berita, catatan broker, jadwal, kondisi pasar). Opsional', key='kantor_teks')
    auto_fund = st.checkbox('Ambil fundamental, berita, dan jadwal otomatis dari Yahoo', value=True)

    if st.button('Jalankan kantor agen', key='btn_kantor', type='primary'):
        if not kunci():
            st.error('GEMINI_API_KEY belum diisi di Secrets.')
        elif not kodes:
            st.warning('Isi minimal satu kode saham.')
        else:
            with st.status('Kantor agen bekerja...', expanded=True) as status:
                try:
                    st.session_state['kantor'] = jalankan_kantor(kodes, modal, risiko, foto, teks_user, auto_fund, status)
                    status.update(label='Selesai', state='complete', expanded=False)
                except Exception as e:
                    status.update(label='Gagal', state='error')
                    st.error('Kantor agen gagal: ' + str(e)[:200])
    tampil_kantor()
    with st.expander('Jurnal trading dan PELATIH'):
        halaman_jurnal()


# ---------- Utama ----------
tema.terapkan()
tema.header(*live.status_bursa())
tema.bar_pasar(get_pasar_dunia())
if not kunci():
    st.warning('GEMINI_API_KEY belum diisi di Secrets, jadi agen AI belum bisa dipakai.')

tab_term, tab_pasar, tab_live, tab_scan, tab_analisis, tab_kantor, tab_riset, tab_tanya, tab_arena = st.tabs(
    ['🖥️ Terminal', '🌅 Pasar', '📈 Live', '🔍 Scanner', '🧪 Analisis', '🏢 Kantor Agen', '🌐 Riset Web', '💬 Tanya AI', '⚔️ Arena'])
with tab_pasar:
    halaman_pasar()
with tab_live:
    halaman_live()
with tab_scan:
    halaman_scanner()
with tab_analisis:
    halaman_analisis()
    tampil_analisis()
with tab_kantor:
    halaman_kantor()
with tab_riset:
    halaman_riset()
with tab_tanya:
    halaman_tanya()
with tab_arena:
    halaman_arena()
# Terminal diisi paling akhir supaya membaca hasil fitur lain dari run yang sama (urutan tab tetap pertama).
with tab_term:
    halaman_terminal(list(EMITEN))

st.caption('Alat bantu analisis, bukan nasihat keuangan. Keputusan akhir ada di kamu.')
