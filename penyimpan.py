"""Penyimpanan permanen tanpa Streamlit: Supabase (lewat REST) atau berkas lokal sebagai cadangan.

Dua backend punya antarmuka sama, jadi aplikasi dan tugas terjadwal memakai kode yang sama:
  kv_get / kv_set                      -> data kecil bebas bentuk (watchlist, jurnal, simulasi, alert, ...)
  sinyal_upsert / sinyal_semua / sinyal_aktif
  skor_upsert / skor_semua
"""
import datetime as dt
import json
import os

import requests

from rekam import AKTIF, KOLOM_SINYAL, KOLOM_SKOR

TIMEOUT = 20


def _sekarang():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def _hanya(baris, kolom):
    return {k: b.get(k) for b in [baris] for k in kolom if k in b}


class Supabase:
    nama = 'Supabase'

    def __init__(self, url, kunci):
        self.url = url.strip().rstrip('/')
        k = kunci.strip()
        self.h = {'apikey': k, 'Content-Type': 'application/json'}
        if not k.startswith('sb_'):
            # Kunci lama (service_role, berbentuk JWT) juga dikirim sebagai Bearer.
            # Kunci baru (sb_secret_...) bukan JWT: cukup header apikey, Bearer akan ditolak gateway.
            self.h['Authorization'] = 'Bearer ' + k

    def _ke(self, tabel):
        return f'{self.url}/rest/v1/{tabel}'

    def _periksa(self, r):
        if r.status_code >= 300:
            raise RuntimeError(f'Supabase {r.status_code}: {r.text[:200]}')
        return r

    def _ambil(self, tabel, **params):
        r = requests.get(self._ke(tabel), headers=self.h, params=params, timeout=TIMEOUT)
        return self._periksa(r).json()

    def _upsert(self, tabel, baris, konflik):
        h = dict(self.h, Prefer='resolution=merge-duplicates,return=minimal')
        for i in range(0, len(baris), 200):
            r = requests.post(self._ke(tabel), headers=h, params={'on_conflict': konflik}, data=json.dumps(baris[i:i + 200]),
                              timeout=TIMEOUT)
            self._periksa(r)

    def kv_get(self, kunci, default=None):
        hasil = self._ambil('kv', kunci='eq.' + kunci, select='nilai')
        return hasil[0]['nilai'] if hasil else default

    def kv_set(self, kunci, nilai):
        self._upsert('kv', [{'kunci': kunci, 'nilai': nilai, 'diubah': _sekarang()}], 'kunci')

    def sinyal_upsert(self, daftar):
        if daftar:
            self._upsert('sinyal', [_hanya(x, KOLOM_SINYAL) for x in daftar], 'id')

    def sinyal_semua(self, limit=1000):
        return self._ambil('sinyal', select='*', order='tanggal.desc,dibuat.desc', limit=limit)

    def sinyal_aktif(self):
        return self._ambil('sinyal', select='*', status='in.(' + ','.join(AKTIF) + ')', order='tanggal.asc', limit=1000)

    def skor_upsert(self, daftar):
        if daftar:
            self._upsert('skor_harian', [_hanya(x, KOLOM_SKOR) for x in daftar], 'id')

    def skor_semua(self, limit=5000):
        return self._ambil('skor_harian', select='*', order='tanggal.desc', limit=limit)


class Lokal:
    """Berkas JSON di folder data_lokal/. Di Streamlit Cloud hilang saat reboot; di komputer sendiri permanen."""
    nama = 'Lokal sementara'

    def __init__(self, folder=None):
        self.folder = folder or os.environ.get('DATA_LOKAL') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data_lokal')

    def _berkas(self, nama):
        return os.path.join(self.folder, nama + '.json')

    def _baca(self, nama, default):
        try:
            with open(self._berkas(nama), encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return default

    def _tulis(self, nama, data):
        os.makedirs(self.folder, exist_ok=True)
        tmp = self._berkas(nama) + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, default=str)
        os.replace(tmp, self._berkas(nama))

    def kv_get(self, kunci, default=None):
        return self._baca('kv', {}).get(kunci, default)

    def kv_set(self, kunci, nilai):
        d = self._baca('kv', {})
        d[kunci] = nilai
        self._tulis('kv', d)

    def _upsert(self, nama, daftar, kolom):
        d = self._baca(nama, {})
        for x in daftar:
            d[x['id']] = {**d.get(x['id'], {}), **_hanya(x, kolom)}
        self._tulis(nama, d)

    def sinyal_upsert(self, daftar):
        if daftar:
            self._upsert('sinyal', daftar, KOLOM_SINYAL)

    def sinyal_semua(self, limit=1000):
        d = list(self._baca('sinyal', {}).values())
        return sorted(d, key=lambda x: (x.get('tanggal') or '', x.get('dibuat') or ''), reverse=True)[:limit]

    def sinyal_aktif(self):
        return sorted((x for x in self._baca('sinyal', {}).values() if x.get('status') in AKTIF), key=lambda x: x.get('tanggal') or '')

    def skor_upsert(self, daftar):
        if daftar:
            self._upsert('skor_harian', daftar, KOLOM_SKOR)

    def skor_semua(self, limit=5000):
        d = list(self._baca('skor_harian', {}).values())
        return sorted(d, key=lambda x: x.get('tanggal') or '', reverse=True)[:limit]


def dari_env(env=None):
    """Supabase jika SUPABASE_URL dan SUPABASE_KEY ada, selain itu None."""
    env = os.environ if env is None else env
    if env.get('SUPABASE_URL') and env.get('SUPABASE_KEY'):
        return Supabase(env['SUPABASE_URL'], env['SUPABASE_KEY'])
    return None
