"""Tanya AI dan Arena (Sidang Saham + Simulasi modal virtual)."""
import json
import re
import time

import pandas as pd
import streamlit as st

import live
import simulasi as sm
from fitur_web import angka_id, jalankan_web, pasar_hari_ini, riset_terbaru
from gemini import blok_gambar, jalankan, kunci
from jejak import catat
from kantor import ambil_json, bersihkan_sidang, hitung_indikator, ringkas_saham, stat_jurnal

SIM_AWAL = 10_000_000
BUKAN_KODE = {'BELI', 'SKIP', 'TUNGGU', 'IHSG', 'IDX', 'LOT', 'HOLD', 'SELL', 'BUY', 'STOP', 'LOSS', 'TAKE', 'PROFIT',
              'TREN', 'NAIK', 'TURUN', 'AMAN', 'SAHAM', 'MANA', 'YANG', 'KENAPA', 'DATA', 'BAIK', 'ARAH', 'ATAU'}
CHIPS = [
    ('Jelaskan chart', 'Jelaskan chart ini: tren, support, resisten, dan sinyalnya.'),
    ('Cek risiko', 'Apa risiko terbesar dari saham ini?'),
    ('Bandingkan', 'Bandingkan saham-saham ini, mana yang lebih layak dan kenapa?'),
    ('Support & resisten', 'Tentukan level support dan resisten dari chart ini.'),
    ('Ringkas hasil', 'Ringkas hasil Kantor Agen terakhir. Mana yang paling layak diprioritaskan, dan kenapa?'),
]
IKON_PUTUSAN = {'BELI': '🟢', 'TUNGGU': '🟡', 'SKIP': '🔴'}


def rp(n):
    return 'Rp' + angka_id(n, 0)


def rp_s(n):
    return ('-' if n < 0 else '+') + 'Rp' + angka_id(abs(n), 0)


def waktu_str():
    return live.sekarang().strftime('%d-%m %H:%M')


# ---------- Data dari fitur lain ----------
def rencana_kantor():
    """Rencana per saham dari hasil Kantor Agen yang punya level valid: {kode: {...}}."""
    h = st.session_state.get('kantor')
    hasil = {}
    for k, x in (h['saham'].items() if h else []):
        ks = x['kasir']
        if not ks:
            continue
        a = x['lap'].get('ANALIS') or {}
        hasil[k] = {'kode': k, 'gaya': a.get('gaya') or '-', 'beli': ks['entry'], 'tp': ks['tp'], 'sl': ks['sl'],
                    'lot': ks['lot'], 'rr': ks['rr'], 'putusan': x['putusan']['putusan']}
    return hasil


def kode_dari_teks(q):
    hasil = []
    for k in re.findall(r'\b[A-Z]{4}\b', q):
        if k not in BUKAN_KODE and k not in hasil:
            hasil.append(k)
    return hasil[:3]


def konteks_tanya(fokus, pakai_hasil, q):
    k = {}
    p = pasar_hari_ini()
    if p:
        k['cek_pasar_hari_ini'] = {x: p[x] for x in ('keputusan', 'kondisi', 'skor', 'ukuran', 'gaya')}
    ris = riset_terbaru()
    if ris:
        k['riset_web'] = {kode: {'putusan_web': v['r'].get('putusan_web'), 'ringkas': v['r'].get('ringkas'),
                                 'tanggal': f'{v["t"]:%Y-%m-%d}'} for kode, v in list(ris.items())[:8]}
    radar = st.session_state.get('radar')
    if radar:
        k['radar'] = {'tanggal_data': radar['r'].get('tanggal_data'), 'tema': radar['r'].get('tema'),
                      'pilihan': [x.get('kode') for x in (radar['r'].get('pilihan') or []) if isinstance(x, dict)]}
    h = st.session_state.get('kantor')
    if pakai_hasil:
        if h:
            urut = sorted(h['saham'].items(), key=lambda kv: ['BELI', 'TUNGGU', 'SKIP'].index(kv[1]['putusan']['putusan']))
            k['hasil_kantor_agen'] = {'waktu': f'{h["waktu"]:%Y-%m-%d %H:%M}', 'saham': [
                {'kode': kode, 'putusan': x['putusan']['putusan'], 'keyakinan': x['putusan']['keyakinan'],
                 'gaya': (x['lap'].get('ANALIS') or {}).get('gaya'), 'harga': x['teknikal']['harga'],
                 'rencana_kasir': x['kasir'], 'alasan': x['putusan']['alasan'], 'peringatan': x['putusan']['peringatan']}
                for kode, x in urut[:10]]}
        stat = stat_jurnal(st.session_state.get('jurnal'))
        if stat:
            k['jurnal_statistik'] = stat
    if fokus and h and fokus in h['saham']:
        x = h['saham'][fokus]
        k['saham_fokus'] = {'kode': fokus, 'teknikal': x['teknikal'], 'laporan_agen': x['lap'], 'KASIR': x['kasir'],
                            'putusan_tim': x['putusan']}
    kodes = kode_dari_teks(q)
    if kodes:
        lv = live.harga_live(tuple(kodes))
        if lv:
            k['harga_yahoo_tertunda'] = {c: {'harga': round(v['harga']), 'ubah_pct': round(v['ubah_pct'], 2),
                                             'bar_terakhir': f'{v["waktu"]:%Y-%m-%d %H:%M} WIB'} for c, v in lv.items()}
    return k or '(tidak ada konteks dari aplikasi)'


# ---------- Tanya AI ----------
def _tambah_q(teks):
    sekarang = st.session_state.get('tanya_q', '')
    st.session_state['tanya_q'] = (sekarang + ' ' if sekarang else '') + teks


def _hapus_chat():
    st.session_state['chat'] = []


def tanya(q, foto, pakai_hasil, bayi, web, fokus, chat):
    gambar = blok_gambar(foto)[:6]
    riwayat = [{'peran': 'pengguna' if m['r'] == 'u' else 'asisten', 'isi': m['t'][:700]} for m in chat[-6:] if m.get('t')]
    payload = {'tanggal': live.sekarang().strftime('%Y-%m-%d'), 'pertanyaan': q, 'mode_bahasa_bayi': bayi,
               'konteks': konteks_tanya(fokus, pakai_hasil, q), 'percakapan_sebelumnya': riwayat,
               'screenshot': 'terlampir' if gambar else 'tidak ada'}
    if web:
        teks, sumber, _ = jalankan_web('TANYA_WEB', payload, 3000, gambar)
    else:
        teks, sumber = jalankan('TANYA', payload, 3000, gambar), []
    return teks.strip() or '(jawaban kosong)', sumber, len(gambar)


def halaman_tanya():
    chat = st.session_state.setdefault('chat', [])
    st.caption('Lampirkan screenshot atau tanya langsung soal saham. Jawaban memakai hasil Cek pasar, Riset Web, Radar, '
               'dan Kantor Agen yang sudah kamu jalankan. Kalau datanya tidak ada, AI bilang tidak tahu.')
    if not chat:
        with st.chat_message('assistant'):
            st.write('Halo bro! Kirim screenshot chart atau tanya apa saja soal saham. Aku jawab dari yang kamu kirim '
                     'dan hasil analisis di aplikasi ini.')
    for m in chat:
        with st.chat_message('user' if m['r'] == 'u' else 'assistant'):
            st.markdown(m['t'])
            if m.get('n'):
                st.caption(f'📎 {m["n"]} screenshot')
            if m.get('sumber'):
                with st.expander(f'Sumber web ({len(m["sumber"])})'):
                    for s in m['sumber'][:8]:
                        st.markdown(f'- [{s["judul"]}]({s["url"]})')

    for kol, (label, teks) in zip(st.columns(len(CHIPS)), CHIPS):
        kol.button(label, key='chip_' + label, on_click=_tambah_q, args=(teks,), width='stretch')
    c1, c2, c3 = st.columns(3)
    pakai_hasil = c1.checkbox('Pakai hasil Kantor Agen & jurnalku', value=True, key='tanya_ctx')
    bayi = c2.checkbox('Bahasa bayi', key='tanya_bayi')
    web = c3.checkbox('Boleh cari di web', key='tanya_web')
    kantor = st.session_state.get('kantor')
    fokus = st.selectbox('Fokus saham (opsional)', ['-'] + (list(kantor['saham']) if kantor else []), key='tanya_fokus')
    with st.form('tanya_form', clear_on_submit=True):
        q = st.text_area('Pertanyaan', key='tanya_q', height=100,
                         placeholder='Contoh: Kenapa BBRI dikasih BELI? Atau lampirkan chart lalu tanya.')
        foto = st.file_uploader('Screenshot (opsional)', type=['png', 'jpg', 'jpeg', 'webp'], accept_multiple_files=True)
        kirim = st.form_submit_button('Kirim', type='primary')
    st.button('Hapus chat', on_click=_hapus_chat, key='tanya_hapus')
    if not kirim:
        return
    q = q.strip() or ('Jelaskan screenshot ini.' if foto else '')
    if not q:
        st.warning('Tulis pertanyaan atau lampirkan screenshot.')
        return
    if not kunci():
        st.error('GEMINI_API_KEY belum diisi di Secrets.')
        return
    try:
        with st.spinner('Mikir dulu...'):
            jawab, sumber, n = tanya(q, foto, pakai_hasil, bayi, web, None if fokus == '-' else fokus, chat)
    except Exception as e:
        st.error('Gagal menjawab: ' + str(e)[:200])
        return
    chat.append({'r': 'u', 't': q, 'n': n})
    chat.append({'r': 'a', 't': jawab, 'sumber': sumber})
    del chat[:-40]
    st.rerun()


# ---------- Sidang Saham ----------
def data_sidang(kode):
    h = st.session_state.get('kantor')
    if h and kode in h['saham']:
        x = h['saham'][kode]
        data = {'teknikal': x['teknikal'], 'laporan_agen': x['lap'], 'KASIR': x['kasir'],
                'putusan_tim': {n: x['putusan'][n] for n in ('putusan', 'keyakinan', 'alasan', 'peringatan')}}
    else:
        harian = live.get_harian_banyak((kode,), '1y').get(kode)
        if harian is None:
            raise ValueError(f'Data {kode} tidak ditemukan di Yahoo')
        d = hitung_indikator(live.sambung_live(harian, live.harga_live((kode,)).get(kode)))
        if len(d) < 60 or d['MA50'].isna().iloc[-1]:
            raise ValueError(f'Data {kode} terlalu sedikit')
        data = {'teknikal': ringkas_saham(kode, d),
                'catatan': 'Belum ada analisis Kantor Agen untuk saham ini; hanya data teknikal Yahoo.'}
    r = riset_terbaru().get(kode)
    if r:
        data['riset_web'] = {x: r['r'].get(x) for x in ('putusan_web', 'ringkas', 'poin_plus', 'poin_minus')}
    return data


def mulai_sidang(kode, note):
    data = data_sidang(kode)
    p = pasar_hari_ini()
    payload = {'kode': kode, 'tanggal': live.sekarang().strftime('%Y-%m-%d'), 'data': data,
               'cek_pasar': {x: p[x] for x in ('keputusan', 'kondisi', 'skor')} if p else None,
               'catatan_pengguna': note.strip()[:600] or None}
    H = bersihkan_sidang(ambil_json(jalankan('SIDANG', payload, 4000)))
    if not H:
        raise ValueError('Naskah sidang kosong atau tidak terbaca. Coba lagi.')
    st.session_state['sidang'] = {'kode': kode, 'H': H, 'palu': None, 'anim': True, 'info': ''}
    catat('SIDANG', f'{kode}: hakim memutuskan {H["putusan"]}', 'ok')


def _pilih_kode(kode):
    st.session_state['sd_kode'] = kode


def _palu(palu):
    s = st.session_state['sidang']
    s['palu'] = palu
    riwayat = st.session_state.setdefault('riwayat_sidang', [])
    riwayat.insert(0, {'t': waktu_str(), 'kode': s['kode'], 'hakim': s['H']['putusan'], 'palu': palu})
    del riwayat[20:]
    catat('SIDANG', f'{s["kode"]}: palumu {palu} (hakim {s["H"]["putusan"]})')


def _ikuti_sim():
    s = st.session_state['sidang']
    rencana = rencana_kantor().get(s['kode'])
    if not rencana or rencana['lot'] < 1:
        s['info'] = 'Tidak ada rencana level valid dari Kantor Agen untuk saham ini.'
        return
    ok, pesan = sm.sim_buka(st.session_state.setdefault('sim', sm.sim_baru(SIM_AWAL)), 'u', rencana, waktu_str())
    s['info'] = ('✓ ' if ok else '') + pesan + (' (lihat tab Simulasi)' if ok else '')


def tampil_sidang():
    s = st.session_state.get('sidang')
    if not s:
        return
    H, kode = s['H'], s['kode']
    animasi = s.pop('anim', False)

    def jeda():
        if animasi:
            time.sleep(0.9)
    st.markdown(f'#### SIDANG {kode} DIBUKA ⚖️')
    for i, r in enumerate(H['ronde']):
        st.markdown(f'**RONDE {i + 1}**')
        with st.chat_message('user', avatar='🐂'):
            st.markdown('**BANTENG** · ' + r['banteng'])
        jeda()
        with st.chat_message('assistant', avatar='🐻'):
            st.markdown('**BERUANG** · ' + r['beruang'])
        jeda()
    with st.chat_message('assistant', avatar='⚖️'):
        st.markdown('**HAKIM (KOORDINATOR)**')
        st.subheader(f'{IKON_PUTUSAN[H["putusan"]]} {H["putusan"]}')
        if H['alasan']:
            st.write(H['alasan'])
        if H['syarat']:
            st.markdown('**Syarat masuk:** ' + H['syarat'])
        tot = (H['banteng'] + H['beruang']) or 1
        st.progress(H['banteng'] / tot, text=f'🐂 {angka_id(H["banteng"], 1)}/10 · 🐻 {angka_id(H["beruang"], 1)}/10')
    if s['palu'] is None:
        st.markdown('Sekarang giliranmu, ketok palu:')
        c = st.columns(3)
        for kol, pal in zip(c, ('BELI', 'TUNGGU', 'SKIP')):
            kol.button(f'{IKON_PUTUSAN[pal]} {pal}', key='palu_' + pal, on_click=_palu, args=(pal,), width='stretch')
    else:
        st.success(f'Palumu: **{s["palu"]}** · ' + ('sama dengan hakim ✓' if s['palu'] == H['putusan']
                                                   else f'beda dengan hakim ({H["putusan"]})'))
        if s['palu'] == 'BELI' and kode in rencana_kantor():
            st.button('Ikuti (simulasi)', key='sd_ikuti', on_click=_ikuti_sim)
        if s.get('info'):
            st.caption(s['info'])


def halaman_sidang():
    st.caption('Banteng (pro beli) lawan Beruang (kontra) berdebat 3 ronde. KOORDINATOR jadi hakim, kamu yang ketok palu.')
    kantor = st.session_state.get('kantor')
    if kantor:
        kandidat = [k for k, x in sorted(kantor['saham'].items(),
                                         key=lambda kv: ['BELI', 'TUNGGU', 'SKIP'].index(kv[1]['putusan']['putusan']))][:10]
        for kol, k in zip(st.columns(len(kandidat)), kandidat):
            kol.button(f'{k} {IKON_PUTUSAN[kantor["saham"][k]["putusan"]["putusan"]]}', key='sdc_' + k,
                       on_click=_pilih_kode, args=(k,), width='stretch')
    else:
        st.caption('Belum ada hasil Kantor Agen. Ketik kode saham di bawah; sidang memakai data teknikal Yahoo.')
    kode = st.text_input('Kode saham', key='sd_kode', placeholder='contoh: BBRI').strip().upper()
    note = st.text_input('Catatan untuk sidang (opsional)', key='sd_note')
    if st.button('⚖️ Mulai sidang', key='btn_sidang', type='primary'):
        if not kunci():
            st.error('GEMINI_API_KEY belum diisi di Secrets.')
        elif not re.fullmatch(r'[A-Z]{4}', kode):
            st.warning('Isi kode saham 4 huruf dulu.')
        else:
            try:
                with st.spinner('Hakim menyiapkan sidang...'):
                    mulai_sidang(kode, note)
            except Exception as e:
                st.error('Sidang gagal: ' + str(e)[:200])
    tampil_sidang()
    st.markdown('**Riwayat sidang**')
    riwayat = st.session_state.get('riwayat_sidang', [])
    if riwayat:
        st.dataframe(pd.DataFrame([{'Waktu': x['t'], 'Kode': x['kode'], 'Hakim': x['hakim'], 'Palumu': x['palu'],
                                    'Sama?': '✓' if x['hakim'] == x['palu'] else ''} for x in riwayat[:10]]),
                     hide_index=True, width='stretch')
    else:
        st.caption('Belum ada sidang.')


# ---------- Simulasi modal virtual ----------
def _sim():
    return st.session_state.setdefault('sim', sm.sim_baru(SIM_AWAL))


def _sim_ikuti(kode):
    rencana = rencana_kantor().get(kode)
    if rencana:
        ok, pesan = sm.sim_buka(_sim(), 'u', rencana, waktu_str())
        _sim()['log'] = [f'{kode}: {pesan}']


def _sim_perbarui(kode, kunci_input):
    harga = st.session_state.get(kunci_input) or 0
    if harga > 0:
        sm.sim_harga(_sim(), 'u', kode, float(harga), waktu_str())


def _sim_jual(kode):
    s = _sim()['u']
    for i, p in enumerate(s['pos']):
        if p['kode'] == kode:
            sm.sim_tutup(_sim(), 'u', i, p.get('last') or p['beli'], 'Dijual', waktu_str())
            break


def _sim_sinkron():
    sim = _sim()
    kodes = sorted({p['kode'] for sisi in ('u', 'a') for p in sim[sisi]['pos']})
    px = {k: v['harga'] for k, v in live.harga_live(tuple(kodes)).items()} if kodes else {}
    rencana = [v for v in rencana_kantor().values() if v['putusan'] == 'BELI']
    sm.sim_sinkron(sim, px, rencana, waktu_str())
    if not sim['log']:
        sim['log'] = ['Tidak ada perubahan']
    for baris in sim['log']:
        catat('SIMULASI', baris)


def _sim_reset(modal):
    st.session_state['sim'] = sm.sim_baru(int(modal))


def halaman_simulasi():
    sim = _sim()
    st.caption('Latihan tanpa uang asli: kamu lawan Tim AI. Harga diperbarui dari Yahoo (tertunda 10-15 menit) saat kamu menekan '
               'tombol di bawah, jadi TP/SL hanya terdeteksi pada saat itu, bukan terus-menerus.')
    u, a = sm.ringkas_sisi(sim, 'u'), sm.ringkas_sisi(sim, 'a')
    lead = 0 if abs(u['ekuitas'] - a['ekuitas']) < 1 else (1 if u['ekuitas'] > a['ekuitas'] else 2)
    c1, c2 = st.columns(2)
    for kol, nama, r, menang in ((c1, 'Kamu', u, lead == 1), (c2, 'Tim AI', a, lead == 2)):
        kol.metric(nama + (' 👑' if menang else ''), rp(r['ekuitas']), f'{r["return_pct"]:+.2f}%'.replace('.', ','))
        kol.caption(f'{r["menang"]}M / {r["kalah"]}K · {r["terbuka"]} terbuka')
    st.button('Perbarui harga (Yahoo) & jalankan Tim AI', key='sim_sinkron', on_click=_sim_sinkron, type='primary')
    if sim['log']:
        st.caption('Terakhir: ' + '; '.join(sim['log']))

    beli = [k for k, v in rencana_kantor().items() if v['putusan'] == 'BELI' and v['lot'] >= 1]
    if beli:
        d1, d2 = st.columns([3, 1])
        pilih = d1.selectbox('Ikuti rencana BELI dari Kantor Agen', beli, key='sim_pilih')
        d2.button('Ikuti (simulasi)', key='sim_ikuti', on_click=_sim_ikuti, args=(pilih,))

    st.markdown('**Posisi terbuka kamu**')
    if not sim['u']['pos']:
        st.caption('Belum ada. Ikuti rencana BELI di atas, atau dari hasil sidang. Kas: ' + rp(sim['u']['kas']))
    for p in sim['u']['pos']:
        pl = (p['last'] - p['beli']) * p['lot'] * 100
        with st.container(border=True):
            st.markdown(f'**{p["kode"]}** {p["lot"]} lot · beli {angka_id(p["beli"], 0)} → {angka_id(p["last"], 0)} · '
                        f'TP {angka_id(p["tp"], 0)} · SL {angka_id(p["sl"], 0)} · **{rp_s(pl)}**')
            k1, k2, k3 = st.columns([2, 1, 1])
            kunci_input = 'simhp_' + p['kode']
            k1.number_input('Harga sekarang', min_value=0, step=1, key=kunci_input, label_visibility='collapsed',
                            placeholder='Harga sekarang')
            k2.button('Perbarui', key='simup_' + p['kode'], on_click=_sim_perbarui, args=(p['kode'], kunci_input))
            k3.button('Jual sekarang', key='simjl_' + p['kode'], on_click=_sim_jual, args=(p['kode'],))
    if sim['a']['pos']:
        st.markdown('**Posisi Tim AI**')
        st.dataframe(pd.DataFrame([{'Kode': p['kode'], 'Lot': p['lot'], 'Beli': angka_id(p['beli'], 0),
                                    'Terakhir': angka_id(p['last'], 0),
                                    'P/L': rp_s((p['last'] - p['beli']) * p['lot'] * 100)} for p in sim['a']['pos']]),
                     hide_index=True, width='stretch')

    st.markdown('**Riwayat**')
    rw = ([dict(x, s='Kamu') for x in sim['u']['rw']] + [dict(x, s='Tim AI') for x in sim['a']['rw']])
    rw.sort(key=lambda x: x.get('t', ''), reverse=True)
    if rw:
        st.dataframe(pd.DataFrame([{'Waktu': x['t'], 'Kode': x['kode'], 'Siapa': x['s'], 'Status': x['status'],
                                    'P/L': rp_s(x['pl'])} for x in rw[:10]]), hide_index=True, width='stretch')
    else:
        st.caption('Belum ada transaksi selesai.')

    with st.expander('Pengaturan simulasi'):
        modal = st.number_input('Modal awal (Rp)', min_value=1_000_000, value=int(sim['modal']), step=1_000_000, key='sim_modal')
        yakin = st.checkbox('Saya yakin mau mulai ulang (semua posisi dan riwayat hilang)', key='sim_yakin')
        if yakin:
            st.button('Mulai ulang', key='sim_reset', on_click=_sim_reset, args=(modal,))
        st.download_button('Unduh simulasi & riwayat sidang (JSON)',
                           json.dumps({'sim': sim, 'sidang': st.session_state.get('riwayat_sidang', [])},
                                      ensure_ascii=False, default=str), 'arena.json', 'application/json')
        up = st.file_uploader('Muat simulasi (JSON)', type=['json'], key='sim_muat')
        if up is not None and st.session_state.get('sim_token') != (up.name, up.size):
            try:
                d = json.loads(up.getvalue())
                if not all(k in d['sim'] for k in ('modal', 'u', 'a')):
                    raise ValueError('format tidak dikenal')
                st.session_state['sim'] = d['sim']
                st.session_state['riwayat_sidang'] = d.get('sidang', [])
                st.session_state['sim_token'] = (up.name, up.size)
                st.rerun()
            except Exception as e:
                st.error('File tidak terbaca: ' + str(e)[:120])


def halaman_arena():
    t1, t2 = st.tabs(['⚖️ Sidang Saham', '💰 Simulasi'])
    with t1:
        halaman_sidang()
    with t2:
        halaman_simulasi()
