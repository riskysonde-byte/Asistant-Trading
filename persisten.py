"""Penghubung Streamlit untuk penyimpanan permanen: pilih backend, simpan dan muat state sesi, catat sinyal."""
import hashlib
import json
import logging
import time

import pandas as pd
import streamlit as st

import live
import rekam
from gemini import rahasia
from jejak import catat
from kantor import KOLOM_JURNAL, level_valid
from penyimpan import Lokal, Supabase

LOG = logging.getLogger('persisten')
KUNCI_STATE = 'status_app'
JEDA_SIMPAN = 4          # detik, supaya tidak menulis tiap interaksi


@st.cache_resource(show_spinner=False)
def _backend(url, kunci, ada_password):
    if url and kunci:
        return Supabase(url, kunci) if ada_password else None
    return Lokal()


def db():
    """Backend penyimpanan, atau None bila Supabase dipasang tanpa APP_PASSWORD (data pribadi tidak boleh terbuka untuk umum)."""
    return _backend(str(rahasia('SUPABASE_URL') or ''), str(rahasia('SUPABASE_KEY') or ''), bool(rahasia('APP_PASSWORD')))


def status():
    """(nama backend, keterangan, aman)"""
    d = db()
    if d is None:
        return 'Nonaktif', 'Supabase terpasang tetapi APP_PASSWORD belum diisi di Secrets. Isi dulu agar data tidak terbuka untuk umum.', False
    if d.nama == 'Supabase':
        return 'Supabase', 'Data tersimpan permanen.', True
    return 'Lokal sementara', 'Tersimpan di server aplikasi; hilang saat Reboot app. Pasang Supabase agar permanen.', True


# ---------- Simpan dan muat state sesi ----------
def _ambil_state():
    s = st.session_state
    jurnal, riset = s.get('jurnal'), s.get('riset')
    return {
        'watchlist': s.get('watchlist'),
        'jurnal': json.loads(jurnal.to_json(orient='records')) if isinstance(jurnal, pd.DataFrame) else None,
        'sim': s.get('sim'),
        'riwayat_sidang': s.get('riwayat_sidang'),
        'riset': {k: {**v, 't': v['t'].isoformat()} for k, v in riset.items()} if riset else None,
        'chat': s.get('chat'),
    }


def _hash(data):
    return hashlib.md5(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def muat_awal():
    """Pulihkan state dari penyimpanan sekali per sesi. Panggil sebelum widget dibuat."""
    s = st.session_state
    if s.get('_muat_selesai'):
        return
    s['_muat_selesai'] = True
    d = db()
    if d is None:
        return
    try:
        data = d.kv_get(KUNCI_STATE, {}) or {}
    except Exception as e:
        LOG.exception('muat_awal gagal')
        s['simpan_galat'] = str(e)[:160]
        return
    if data.get('watchlist'):
        s['watchlist'] = data['watchlist']
    if data.get('jurnal'):
        s['jurnal'] = pd.DataFrame(data['jurnal']).reindex(columns=KOLOM_JURNAL)
    for k in ('sim', 'riwayat_sidang', 'chat'):
        if data.get(k):
            s[k] = data[k]
    if data.get('riset'):
        s['riset'] = {k: {**v, 't': pd.Timestamp(v['t']).to_pydatetime()} for k, v in data['riset'].items()}
    s['_hash_simpan'] = _hash(_ambil_state())


def sinkron():
    """Simpan state bila berubah. Panggil di akhir skrip. Kegagalan tidak pernah menghentikan aplikasi."""
    s = st.session_state
    d = db()
    if d is None or time.time() - s.get('_simpan_t', 0) < JEDA_SIMPAN:
        return
    try:
        data = _ambil_state()
        h = _hash(data)
        if h == s.get('_hash_simpan'):
            return
        d.kv_set(KUNCI_STATE, data)
        s['_hash_simpan'], s['_simpan_t'] = h, time.time()
        s.pop('simpan_galat', None)
    except Exception as e:
        LOG.exception('sinkron gagal')
        s['simpan_galat'] = str(e)[:160]


# ---------- Catat sinyal dan skor ----------
def catat_sinyal_kantor(hasil):
    """Catat semua rencana bertingkat valid dari satu run Kantor Agen (termasuk TUNGGU/SKIP sebagai pembanding)."""
    d = db()
    if d is None:
        return 0
    daftar = []
    for k, x in hasil['saham'].items():
        lv = level_valid(x['lap'].get('ANALIS') or {})
        if lv and x['kasir']:
            p = x['putusan']
            daftar.append(rekam.buat_sinyal('kantor', k, lv, gaya=(x['lap'].get('ANALIS') or {}).get('gaya'),
                                            putusan=p['putusan'], keyakinan=p['keyakinan'], rr=x['kasir']['rr']))
    try:
        d.sinyal_upsert(daftar)
        if daftar:
            catat('REKAM', f'{len(daftar)} sinyal dicatat ke Rekam Jejak', 'ok')
        return len(daftar)
    except Exception as e:
        LOG.exception('catat_sinyal_kantor gagal')
        st.session_state['simpan_galat'] = str(e)[:160]
        catat('REKAM', 'Gagal mencatat sinyal: ' + str(e)[:80], 'err')
        return 0


def catat_skor(skor):
    """Simpan snapshot skor bola (satu baris per saham per hari) untuk divalidasi kemudian."""
    d = db()
    if d is None or not skor:
        return 0
    try:
        d.skor_upsert([rekam.buat_skor(x['k'], x['s'], x['l'], x['hn']) for x in skor if x.get('hn')])
        return len(skor)
    except Exception as e:
        LOG.exception('catat_skor gagal')
        st.session_state['simpan_galat'] = str(e)[:160]
        return 0


def evaluasi_sekarang():
    """Evaluasi sinyal aktif dan skor bola dengan data harian terbaru. Hasil: (jumlah sinyal diperbarui, ringkasan skor)."""
    from tugas import pantau
    d = db()
    aktif = d.sinyal_aktif()
    harian = lambda kodes, periode='3mo': live.get_harian_banyak(tuple(kodes), periode) if kodes else {}
    data = harian(sorted({s['kode'] for s in aktif}))
    baru = [rekam.evaluasi(s, data.get(s['kode'])) for s in aktif]
    d.sinyal_upsert(baru)
    ringkas = pantau._perbarui_skor(d, harian, rekam.hari_ini())
    ubah = sum(1 for a, b in zip(aktif, baru) if a['status'] != b['status'])
    return ubah, ringkas
