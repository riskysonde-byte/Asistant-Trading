"""Cek pasar pagi, Radar pasar luas, dan Riset web per saham (Streamlit)."""
import concurrent.futures as cf
import datetime as dt

import pandas as pd
import streamlit as st
import yfinance as yf

import live
from gemini import blok_gambar, jalankan, kunci
from kantor import ambil_json, bersihkan_pasar, kode_valid, kumpul_kode

INDEKS = [
    ('IHSG', '^JKSE'), ('Dow Jones', '^DJI'), ('S&P 500', '^GSPC'), ('Nasdaq', '^IXIC'),
    ('Nikkei 225', '^N225'), ('Hang Seng', '^HSI'), ('USD/IDR', 'USDIDR=X'),
    ('Minyak WTI', 'CL=F'), ('Emas', 'GC=F'), ('Batu bara Newcastle', 'MTF=F'), ('Tembaga', 'HG=F'),
]
HARI = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu']
IKON_PASAR = {'TRADING': '🟢', 'SELEKTIF': '🟡', 'LIBUR': '🔴'}
IKON_RISET = {'MENARIK': '🟢', 'TUNGGU': '🟡', 'HINDARI': '🔴'}


def angka_id(v, nd=2):
    return f'{v:,.{nd}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


@st.cache_data(ttl=300, show_spinner=False)
def get_pasar_dunia():
    """Indeks dunia, kurs, dan komoditas dari Yahoo dalam satu permintaan. Tiap data membawa tanggal bar terakhir."""
    try:
        df = yf.download([s for _, s in INDEKS], period='10d', auto_adjust=False, progress=False,
                         group_by='ticker', threads=True)
    except Exception:
        return []
    hasil = []
    for nama, s in INDEKS:
        try:
            c = df[s]['Close'].dropna()
            if len(c) < 2:
                continue
            hasil.append({'label': nama, 'terakhir': round(float(c.iloc[-1]), 2),
                          'ubah_pct': round(float(c.iloc[-1] / c.iloc[-2] - 1) * 100, 2),
                          'tanggal': f'{c.index[-1]:%Y-%m-%d}'})
        except Exception:
            continue
    return hasil


def pasar_hari_ini():
    """Hasil Cek pasar pagi yang dibuat hari ini (WIB), atau None."""
    p = st.session_state.get('pasar')
    if p and p.get('tanggal') == live.sekarang().date().isoformat():
        return p
    return None


def jalankan_web(nama, payload, max_tokens, gambar=None, boleh_web=True):
    """Coba dengan Google Search; kalau gagal, ulangi tanpa web (hanya bila boleh). Hasil: (teks, sumber, dipakai_web)."""
    try:
        teks, sumber = jalankan(nama, payload, max_tokens, gambar, web=True, sumber=True)
        return teks, sumber, True
    except Exception:
        if not boleh_web:
            raise
        return jalankan(nama, payload, max_tokens, gambar), [], False


# ---------- Cek pasar pagi ----------
def baca_pasar(pakai_web, catatan, foto):
    data = get_pasar_dunia()
    gambar = blok_gambar(foto)
    if not data and not catatan.strip() and not gambar:
        raise ValueError('Data pasar dari Yahoo belum bisa diambil. Coba lagi, atau isi catatan / unggah screenshot.')
    payload = {'tanggal_hari_ini': f'{live.sekarang():%Y-%m-%d} ({HARI[live.sekarang().weekday()]})', 'jam_wib': live.sekarang().strftime('%H:%M'),
               'status_bursa': live.status_bursa()[1], 'data_yahoo': data,
               'catatan_pengguna': catatan.strip() or None, 'screenshot': 'terlampir' if gambar else 'tidak ada',
               'boleh_cari_web': pakai_web}
    if pakai_web:
        teks, sumber, ok_web = jalankan_web('PASAR', payload, 6000, gambar)
    else:
        teks, sumber, ok_web = jalankan('PASAR', payload, 6000, gambar), [], False
    hasil = bersihkan_pasar(ambil_json(teks), len(data) + (1 if gambar or catatan.strip() else 0))
    if not hasil:
        raise ValueError('Jawaban AI tidak terbaca. Coba lagi.')
    hasil.update({'tanggal': live.sekarang().date().isoformat(), 'waktu': live.sekarang(),
                  'data': data, 'sumber': sumber, 'pakai_web': ok_web})
    return hasil


def tampil_pasar():
    p = st.session_state.get('pasar')
    if not p:
        return
    basi = p['tanggal'] != live.sekarang().date().isoformat()
    judul = {'TRADING': 'TRADING', 'SELEKTIF': 'SELEKTIF', 'LIBUR': 'LIBUR DULU'}[p['keputusan']]
    sub = {'LIBUR': 'Hari ini sebaiknya tidak membuka posisi baru.',
           'SELEKTIF': 'Boleh trading, tapi hanya setup terbaik dan posisi dikecilkan.',
           'TRADING': 'Kondisi mendukung, ikuti rencana seperti biasa.'}[p['keputusan']]
    with st.container(border=True):
        st.caption(f'{HARI[p["waktu"].weekday()]} {p["waktu"]:%H:%M} WIB' + (' · KEDALUWARSA, baca ulang' if basi else ' · berlaku hari ini')
                   + (' · dengan pencarian web' if p['pakai_web'] else ' · tanpa pencarian web'))
        st.subheader(f'{IKON_PASAR[p["keputusan"]]} {judul}')
        st.write(sub)
        st.progress(p['skor'] / 100, text=f'Skor pasar {p["skor"]}/100 · {p["kondisi"]}')
        c1, c2 = st.columns(2)
        c1.metric('Gaya yang cocok', ' · '.join(p['gaya']) if p['gaya'] else 'Tidak ada')
        c2.metric('Ukuran posisi', f'{p["ukuran"]}%')
        if p['alasan']:
            st.markdown('**Alasan**\n' + '\n'.join('- ' + x for x in p['alasan']))
        if p['waspada']:
            st.markdown('**Waspada**\n' + '\n'.join('- ' + x for x in p['waspada']))
        if p['level']:
            st.markdown('**Level IHSG** · support ' + (' · '.join(angka_id(v, 0) for v in p['level']['support']) or '-')
                        + ' | resisten ' + (' · '.join(angka_id(v, 0) for v in p['level']['resisten']) or '-'))
        if p['ringkas']:
            st.caption(p['ringkas'])
        if p['data']:
            with st.expander(f'Data yang terbaca ({len(p["data"])})'):
                st.dataframe(pd.DataFrame([{'Data': x['label'], 'Terakhir': angka_id(x['terakhir']),
                                            'Ubah': f'{x["ubah_pct"]:+.2f}%'.replace('.', ','),
                                            'Bar terakhir': x['tanggal']} for x in p['data']]),
                             hide_index=True, width='stretch')
        if p['sumber']:
            with st.expander(f'Sumber web ({len(p["sumber"])})'):
                for s in p['sumber'][:10]:
                    st.markdown(f'- [{s["judul"]}]({s["url"]})')


# ---------- Radar pasar luas ----------
def pindai_radar():
    teks, sumber, ok_web = jalankan_web('RADAR', {'tanggal_hari_ini': live.sekarang().strftime('%Y-%m-%d'),
                                                   'status_bursa': live.status_bursa()[1]}, 8000, boleh_web=False)
    r = ambil_json(teks)
    if not isinstance(r, dict):
        raise ValueError('Jawaban radar tidak terbaca. Coba lagi.')
    asing = r.get('asing') if isinstance(r.get('asing'), dict) else {}
    kodes = kumpul_kode(r.get('gainers'), r.get('losers'), r.get('aktif'), asing.get('beli'), asing.get('jual'),
                        r.get('akumulasi'), r.get('pilihan'))
    # Cek silang dengan Yahoo: angka dari web boleh salah, jadi ditampilkan berdampingan.
    return {'r': r, 'asing': asing, 'yahoo': live.harga_live(tuple(kodes)) if kodes else {},
            'sumber': sumber, 'waktu': live.sekarang()}


def _tabel(daftar, yahoo, kolom_web, judul_web):
    baris = []
    for x in daftar or []:
        if not isinstance(x, dict):
            continue
        k = kode_valid(x.get('kode'))
        if not k:
            continue
        lv = yahoo.get(k)
        baris.append({'Kode': k, judul_web: str(x.get(kolom_web) or '-'),
                      'Yahoo hari ini': f'{lv["ubah_pct"]:+.2f}%'.replace('.', ',') if lv else 'n/a',
                      'Catatan': str(x.get('alasan') or '')})
    return pd.DataFrame(baris)


def tampil_radar():
    h = st.session_state.get('radar')
    if not h:
        return
    r, y = h['r'], h['yahoo']
    with st.container(border=True):
        st.caption(f'Radar pasar luas · dicek {h["waktu"]:%d-%m-%Y %H:%M} WIB · data bursa tanggal {r.get("tanggal_data") or "?"}. '
                   'Angka dari web, bukan real-time. Kolom "Yahoo hari ini" untuk cek silang.')
        if r.get('ringkas'):
            st.write(r['ringkas'])
        if r.get('tema'):
            st.markdown('**Tema:** ' + ' · '.join(str(t) for t in r['tema'][:6]))
        bagian = [('📈 Top naik', _tabel(r.get('gainers'), y, 'ubah_pct', 'Naik (web)')),
                  ('📉 Top turun', _tabel(r.get('losers'), y, 'ubah_pct', 'Turun (web)')),
                  ('🔥 Paling ramai', _tabel(r.get('aktif'), y, 'nilai', 'Nilai (web)')),
                  ('💸 Asing borong', _tabel(h['asing'].get('beli'), y, 'nilai', 'Nilai (web)')),
                  ('🏃 Asing lepas', _tabel(h['asing'].get('jual'), y, 'nilai', 'Nilai (web)')),
                  ('🧲 Akumulasi', _tabel(r.get('akumulasi'), y, 'nilai', 'Nilai (web)'))]
        for judul, tabel in bagian:
            if not tabel.empty:
                with st.expander(f'{judul} ({len(tabel)})'):
                    st.dataframe(tabel, hide_index=True, width='stretch')
        pilihan = _tabel(r.get('pilihan'), y, 'nilai', 'Nilai (web)')
        if not pilihan.empty:
            st.markdown('**⭐ Kandidat pilihan**')
            st.dataframe(pilihan[['Kode', 'Yahoo hari ini', 'Catatan']], hide_index=True, width='stretch')
        kandidat = kumpul_kode(r.get('pilihan'), maks=5)
        if kandidat:
            c1, c2 = st.columns(2)
            c1.button('Pakai kandidat di Kantor Agen', key='radar_ke_kantor', on_click=_set,
                      args=('kantor_daftar', ','.join(kandidat)))
            c2.button('Riset kandidat (tab Riset Web)', key='radar_ke_riset', on_click=_set,
                      args=('riset_in', ', '.join(kandidat[:3])))
        if h['sumber']:
            with st.expander(f'Sumber web ({len(h["sumber"])})'):
                for s in h['sumber'][:12]:
                    st.markdown(f'- [{s["judul"]}]({s["url"]})')


def _set(kunci_state, nilai):
    st.session_state[kunci_state] = nilai


def halaman_pasar():
    st.markdown('### ☀️ Cek pasar pagi')
    st.caption('Lakukan ini dulu saat bursa buka. Angka IHSG, bursa dunia, kurs, dan komoditas ditarik otomatis dari Yahoo. '
               'AI memutuskan hari ini layak trading atau tidak.')
    pakai_web = st.checkbox('Cari berita pasar terbaru di web (Google Search)', value=True, key='pasar_web')
    catatan = st.text_area('Catatan tambahan (opsional): berita, arus asing, dsb.', key='pasar_catatan', height=80)
    foto = st.file_uploader('Screenshot tambahan (opsional)', type=['png', 'jpg', 'jpeg', 'webp'],
                            accept_multiple_files=True, key='pasar_foto')
    if st.button('Baca pasar sekarang', key='btn_pasar', type='primary'):
        if not kunci():
            st.error('GEMINI_API_KEY belum diisi di Secrets.')
        else:
            try:
                with st.spinner('Membaca pasar...'):
                    st.session_state['pasar'] = baca_pasar(pakai_web, catatan, foto)
            except Exception as e:
                st.error('Cek pasar gagal: ' + str(e)[:200])
    tampil_pasar()

    st.markdown('### 🌐 Radar pasar luas')
    st.caption('AI mencari di web: saham top naik/turun, paling ramai, arus asing, tema, dan kandidat. '
               'Hasilnya dicek silang dengan harga Yahoo.')
    if st.button('Pindai pasar luas', key='btn_radar'):
        if not kunci():
            st.error('GEMINI_API_KEY belum diisi di Secrets.')
        else:
            try:
                with st.spinner('Mencari data bursa di web, sekitar 1 menit...'):
                    st.session_state['radar'] = pindai_radar()
            except Exception as e:
                st.error('Radar gagal: ' + str(e)[:200])
    tampil_radar()


# ---------- Riset web per saham ----------
def riset_satu(kode):
    lv = live.harga_live((kode,)).get(kode)
    data = ({'harga': round(lv['harga']), 'ubah_pct': round(lv['ubah_pct'], 2), 'high': round(lv['high']),
             'low': round(lv['low']), 'bar_terakhir': f'{lv["waktu"]:%Y-%m-%d %H:%M} WIB'} if lv else None)
    teks, sumber, _ = jalankan_web('RISET', {'kode': kode, 'data_yahoo': data}, 8000, boleh_web=False)
    r = ambil_json(teks)
    if not isinstance(r, dict):
        raise ValueError(kode + ': jawaban riset tidak terbaca')
    return {'t': live.sekarang(), 'r': r, 'sumber': sumber}


def riset_terbaru(hari=7):
    """Hasil riset yang masih segar, untuk dibaca agen lain."""
    batas = live.sekarang() - dt.timedelta(days=hari)
    return {k: v for k, v in st.session_state.get('riset', {}).items() if v['t'] >= batas}


def tampil_riset():
    hasil = st.session_state.get('riset', {})
    for i, (k, x) in enumerate(sorted(hasil.items(), key=lambda kv: kv[1]['t'], reverse=True)):
        r = x['r']
        p = str(r.get('putusan_web', '')).upper()
        p = p if p in IKON_RISET else 'TUNGGU'
        with st.container(border=True):
            st.markdown(f'**{k}** · {IKON_RISET[p]} **{p}** · {x["t"]:%d-%m-%Y %H:%M} WIB')
            if r.get('harga') or r.get('tren'):
                st.caption(' · '.join(str(v) for v in (r.get('harga'), r.get('tren')) if v))
            if r.get('ringkas'):
                st.write(r['ringkas'])
            for judul, kunci_r in (('👍 Poin plus', 'poin_plus'), ('⚠️ Poin minus', 'poin_minus')):
                if isinstance(r.get(kunci_r), list) and r[kunci_r]:
                    st.markdown(f'**{judul}**\n' + '\n'.join('- ' + str(t) for t in r[kunci_r][:3]))
            for ikon, kunci_r in (('💸 Asing', 'asing'), ('🐋 Bandar', 'bandar'), ('🎯 Analis', 'analis')):
                if r.get(kunci_r):
                    st.markdown(f'{ikon}: {r[kunci_r]}')
            f = r.get('fundamental') if isinstance(r.get('fundamental'), dict) else {}
            fd = [f'{n.upper().replace("LABA_YOY", "Laba")} {f[n]}' for n in ('per', 'pbv', 'roe', 'der', 'laba_yoy')
                  if f.get(n) not in (None, '')]
            if fd:
                st.markdown('📊 ' + ' · '.join(fd))
            if isinstance(r.get('berita'), list) and r['berita']:
                with st.expander('Berita'):
                    for b in r['berita'][:5]:
                        if isinstance(b, dict):
                            st.markdown(f'- {b.get("judul", "")} ({b.get("tanggal", "?")}) · {b.get("sentimen", "")}')
            if x['sumber']:
                with st.expander(f'Sumber web ({len(x["sumber"])})'):
                    for s in x['sumber'][:10]:
                        st.markdown(f'- [{s["judul"]}]({s["url"]})')
    if hasil:
        st.caption('Riset dari berita web, bukan data real-time, dan bisa keliru. Cek sumbernya sebelum bertindak.')


def halaman_riset():
    st.markdown('### 🔎 Tim riset internet')
    st.caption('Gemini browsing sendiri: berita emiten, arus asing, kabar bandar, fundamental, target analis. '
               'Tanpa screenshot. Maksimal 3 kode sekali jalan, sekitar 1 menit.')
    st.text_input('Kode saham (pisahkan koma)', key='riset_in', placeholder='contoh: ANTM, BBRI')
    if st.button('Suruh tim cari', key='btn_riset', type='primary'):
        kodes = [k for k in dict.fromkeys(kode_valid(x) for x in st.session_state.get('riset_in', '').replace(',', ' ').split()) if k][:3]
        if not kunci():
            st.error('GEMINI_API_KEY belum diisi di Secrets.')
        elif not kodes:
            st.warning('Tulis kode saham 4 huruf dulu, contoh ANTM.')
        else:
            st.session_state.setdefault('riset', {})
            with st.spinner('Tim browsing ' + ', '.join(kodes) + '...'):
                with cf.ThreadPoolExecutor(max_workers=3) as ex:
                    futs = {k: ex.submit(riset_satu, k) for k in kodes}
                    for k, f in futs.items():
                        try:
                            st.session_state['riset'][k] = f.result()
                        except Exception as e:
                            st.error(f'{k} gagal: ' + str(e)[:150])
    tampil_riset()
