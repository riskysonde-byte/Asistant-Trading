"""Tab Rekam Jejak: bukti apakah sinyal aplikasi ini berguna, status penyimpanan, notifikasi, dan panduan setel."""
import os
import uuid

import pandas as pd
import streamlit as st

import notif
import persisten
import rekam
from gemini import rahasia
from tema import angka, persen

STATUS = {'belum_masuk': '⏳ Menunggu zona', 'terbuka': '🟢 Berjalan', 'kena_tp': '🎯 Kena TP', 'kena_sl': '🛑 Kena SL',
          'kedaluwarsa': '⌛ Kedaluwarsa', 'tidak_terisi': '➖ Tidak terisi'}
BASE = os.path.dirname(os.path.abspath(__file__))
SQL = os.path.join(BASE, 'sql', 'skema.sql')
PANDUAN = os.path.join(BASE, 'PANDUAN.md')


def _kartu(judul, nilai, ket=''):
    return f'<div><small>{judul}</small><b>{nilai}</b>' + (f'<br><small>{ket}</small>' if ket else '') + '</div>'


def _panel_status():
    nama, ket, aman = persisten.status()
    (st.success if aman and nama == 'Supabase' else st.warning if aman else st.error)(f'**Penyimpanan: {nama}.** {ket}')
    if st.session_state.get('simpan_galat'):
        st.error('Gagal menyimpan: ' + st.session_state['simpan_galat'])
    t_ok = bool(rahasia('TELEGRAM_BOT_TOKEN') and rahasia('TELEGRAM_CHAT_ID'))
    c1, c2 = st.columns([3, 1])
    c1.caption('Telegram: ' + ('token dan chat ID terisi di Secrets.' if t_ok else
                               'belum diisi di Secrets aplikasi (TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID). '
                               'Notifikasi otomatis berjalan lewat GitHub Actions dan memakai rahasia di GitHub, lihat panduan di bawah.'))
    if c2.button('Kirim pesan tes', key='rk_tes', disabled=not t_ok):
        ok, ket = notif.kirim(rahasia('TELEGRAM_BOT_TOKEN'), rahasia('TELEGRAM_CHAT_ID'),
                              '✅ Tes dari Asisten Trading IDX. Notifikasi Telegram sudah tersambung.')
        (st.success if ok else st.error)('Pesan tes ' + ('terkirim, cek Telegram Bos.' if ok else 'gagal: ' + ket))


def _statistik(sinyal):
    st_ = rekam.statistik(sinyal)
    if not st_['semua']:
        st.info('Belum ada sinyal yang selesai. Jalankan **Kantor Agen**: tiap rencana yang punya zona beli, TP, dan SL valid dicatat '
                'otomatis, lalu dinilai dengan harga hari-hari berikutnya.')
    else:
        t = st_['semua']
        st.markdown('<div class="sg">' + _kartu('Win rate', f'{t["win_rate"]}%'.replace('.', ','), f'{t["n"]} sinyal selesai')
                    + _kartu('Rata-rata R', f'{t["rata_r"]:+.2f}R'.replace('.', ','), '1R = jarak entry ke SL')
                    + _kartu('Rata-rata hasil', persen(t['rata_pct']))
                    + _kartu('Berjalan / menunggu', f'{st_["terbuka"]} / {st_["belum_masuk"]}', f'tidak terisi {st_["tidak_terisi"]}')
                    + '</div>', unsafe_allow_html=True)
        if st_['sampel_kecil']:
            st.warning(f'Baru {t["n"]} sinyal selesai. Butuh minimal {rekam.SAMPEL_MIN} supaya angka ini berarti. Sebelum itu anggap hasilnya '
                       'gambaran awal saja, bukan bukti.')
        tabel = []
        for judul, kelompok in (('Putusan', st_['per_putusan']), ('Gaya', st_['per_gaya'])):
            for nama, r in kelompok.items():
                tabel.append({'Kelompok': f'{judul}: {nama}', 'Sinyal': r['n'], 'Win rate': f'{r["win_rate"]}%'.replace('.', ','),
                              'Rata-rata R': f'{r["rata_r"]:+.2f}'.replace('.', ','), 'Rata-rata %': persen(r['rata_pct'])})
        st.dataframe(pd.DataFrame(tabel), hide_index=True, width='stretch')
        pp = st_['per_putusan']
        if pp.get('BELI') and any(pp.get(k) and pp[k]['n'] >= 10 for k in ('TUNGGU', 'SKIP')) and pp['BELI']['n'] >= 10:
            lain = [pp[k]['rata_r'] for k in ('TUNGGU', 'SKIP') if pp.get(k) and pp[k]['n'] >= 10]
            if pp['BELI']['rata_r'] <= max(lain):
                st.warning('Sinyal BELI belum lebih baik daripada TUNGGU/SKIP. Artinya filter AI belum menambah nilai; perketat syaratnya atau jangan terlalu dipercaya.')
            else:
                st.success('Sinyal BELI lebih baik daripada TUNGGU/SKIP. Filter AI tampak menambah nilai (masih perlu sampel lebih besar).')
    return st_


def _tabel_sinyal(sinyal):
    filt = st.multiselect('Tampilkan status', list(STATUS.values()), default=list(STATUS.values()), key='rk_filter')
    baris = []
    for x in sinyal:
        if STATUS[x['status']] not in filt:
            continue
        apung = None
        if x['status'] == 'terbuka' and x.get('harga_terakhir') and x.get('harga_masuk'):
            apung = (x['harga_terakhir'] / x['harga_masuk'] - 1) * 100
        hasil = x.get('hasil_pct') if x.get('hasil_pct') is not None else apung
        baris.append({'Tanggal': x['tanggal'], 'Kode': x['kode'], 'Putusan': x.get('putusan') or '-', 'Gaya': x.get('gaya') or '-',
                      'Zona beli': f'{angka(x["beli_dari"])}-{angka(x["beli_sampai"])}', 'TP': angka(x['tp']), 'SL': angka(x['sl']),
                      'Status': STATUS[x['status']], 'Hasil': persen(hasil) if hasil is not None else '-',
                      'R': f'{x["hasil_r"]:+.2f}'.replace('.', ',') if x.get('hasil_r') is not None else '-'})
    st.dataframe(pd.DataFrame(baris), hide_index=True, width='stretch') if baris else st.caption('Tidak ada sinyal pada filter ini.')


def _validasi_skor(d):
    s = rekam.statistik_skor(d.skor_semua())
    if not s:
        st.info('Belum ada data. Di tab **Terminal**, pilih Seluruh IDX lalu **Muat / perbarui data** tiap hari. Hasilnya muncul setelah 5 hari bursa.')
        return
    tabel = [{'Label': k, 'Saham': v['n'], 'Rata-rata imbal 5 hari': persen(v['rata_ret5']),
              'Naik (hit)': f'{v["hit_pct"]}%'.replace('.', ',')} for k, v in s['per_label'].items()]
    st.dataframe(pd.DataFrame(tabel), hide_index=True, width='stretch')
    kor = '-' if s['korelasi'] is None else f'{s["korelasi"]:+.3f}'.replace('.', ',')
    st.caption(f'{s["n"]} pengamatan · rata-rata semua {persen(s["rata_semua"])} · korelasi peringkat skor dengan imbal: {kor}. '
               'Skor berguna jika BULLISH lebih tinggi dari rata-rata dan BEARISH lebih rendah.')
    if s['sampel_kecil']:
        st.warning('Pengamatan masih sedikit (di bawah 100). Jangan simpulkan dulu.')


def _alert(d):
    alert = d.kv_get('alert', []) or []
    with st.form('rk_alert', clear_on_submit=True):
        c = st.columns([1, 1, 1, 1])
        kode = c[0].text_input('Kode', placeholder='BBCA').strip().upper()
        op = c[1].selectbox('Kondisi', ['naik di atas', 'turun di bawah'])
        harga = c[2].number_input('Harga', min_value=0, step=1)
        if c[3].form_submit_button('Tambah alert'):
            if len(kode) == 4 and harga > 0:
                alert.append({'id': uuid.uuid4().hex[:8], 'kode': kode, 'op': '>=' if op == 'naik di atas' else '<=', 'harga': harga,
                              'aktif': True, 'dibuat': rekam.hari_ini()})
                d.kv_set('alert', alert)
                st.rerun()
            else:
                st.warning('Isi kode 4 huruf dan harga.')
    for a in alert:
        c1, c2 = st.columns([5, 1])
        c1.markdown(f'**{a["kode"]}** {"naik di atas" if a["op"] == ">=" else "turun di bawah"} Rp{angka(a["harga"])} · '
                    + ('✅ sudah terkirim ' + str(a['dikirim']) if a.get('dikirim') else '⏳ menunggu'))
        if c2.button('Hapus', key='rk_hapus_' + a['id']):
            d.kv_set('alert', [x for x in alert if x['id'] != a['id']])
            st.rerun()
    if not alert:
        st.caption('Belum ada alert harga. Alert sinyal (masuk zona beli, kena TP/SL) tidak perlu dibuat, itu otomatis.')


def _panduan():
    with st.expander('Cara setel penyimpanan dan notifikasi (sekali saja)'):
        if os.path.exists(PANDUAN):
            with open(PANDUAN, encoding='utf-8') as f:
                st.markdown(f.read())
        st.markdown('**Isi file SQL (tempel di Supabase → SQL Editor):**')
        with open(SQL, encoding='utf-8') as f:
            st.code(f.read(), language='sql')


def halaman_rekam():
    st.caption('Tiap rencana dari Kantor Agen dicatat lalu dinilai dengan harga hari-hari berikutnya. Ini cara paling jujur untuk tahu '
               'apakah sinyalnya berguna. Aturan penilaian sengaja konservatif: dihitung mulai hari bursa berikutnya, dan bila TP dan SL '
               'tersentuh di hari yang sama dianggap SL lebih dulu.')
    _panel_status()
    d = persisten.db()
    if d is None:
        _panduan()
        return
    if st.button('Perbarui evaluasi sekarang', key='rk_evaluasi', type='primary'):
        try:
            with st.spinner('Mengambil harga harian dan menilai sinyal...'):
                ubah, _ = persisten.evaluasi_sekarang()
            st.success(f'Selesai. {ubah} sinyal berubah status.')
        except Exception as e:
            st.error('Gagal mengevaluasi: ' + str(e)[:200])
    try:
        sinyal = d.sinyal_semua()
        st.markdown('#### Hasil sinyal')
        _statistik(sinyal)
        if sinyal:
            st.markdown('#### Daftar sinyal')
            _tabel_sinyal(sinyal)
        st.markdown('#### Validasi skor bola Terminal')
        _validasi_skor(d)
        st.markdown('#### Alert harga')
        _alert(d)
    except Exception as e:
        st.error('Data rekam jejak belum bisa dibaca: ' + str(e)[:200] + ' Pastikan file SQL sudah dijalankan di Supabase.')
    _panduan()
