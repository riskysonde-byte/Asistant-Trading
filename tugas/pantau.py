"""Tugas terjadwal (GitHub Actions): evaluasi sinyal rekam jejak dan kirim notifikasi Telegram.

Pemakaian:  python tugas/pantau.py intraday   (tiap 15 menit saat bursa buka)
            python tugas/pantau.py harian     (sekali setelah bursa tutup: evaluasi + ringkasan)
Butuh variabel lingkungan: SUPABASE_URL, SUPABASE_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.
Data harga: Yahoo Finance (tertunda sekitar 10-15 menit).
"""
import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import notif  # noqa: E402
import penyimpan  # noqa: E402
import rekam  # noqa: E402

IKON = {'terbuka': '✅ MASUK', 'kena_tp': '🎯 TP KENA', 'kena_sl': '🛑 SL KENA', 'kedaluwarsa': '⌛ KEDALUWARSA',
        'tidak_terisi': '➖ TIDAK TERISI'}
DEKAT_ZONA, DEKAT_SL, DEKAT_TP = 1.003, 1.01, 0.99
IHSG_TURUN = -1.5


def rp(n):
    return 'Rp' + f'{float(n):,.0f}'.replace(',', '.')


def e(x):
    return html.escape(str(x))


# ---------- Data Yahoo ----------
def ambil_harian(kodes, periode='3mo'):
    import yfinance as yf
    if not kodes:
        return {}
    df = yf.download([k + '.JK' for k in kodes], period=periode, auto_adjust=False, progress=False, group_by='ticker', threads=True)
    return rekam.pecah_download(df, kodes)


def ambil_terakhir(kodes):
    """Harga terakhir per menit (tertunda). {kode: harga}"""
    import yfinance as yf
    if not kodes:
        return {}
    df = yf.download([k + '.JK' for k in kodes], period='1d', interval='1m', auto_adjust=False, progress=False,
                     group_by='ticker', threads=True)
    return {k: float(d['Close'].iloc[-1]) for k, d in rekam.pecah_download(df, kodes).items()}


def ambil_ihsg():
    """Perubahan IHSG hari ini dalam persen, atau None."""
    import yfinance as yf
    try:
        c = yf.download('^JKSE', period='5d', auto_adjust=False, progress=False)['Close'].dropna()
        c = c.iloc[:, 0] if getattr(c, 'ndim', 1) == 2 else c
        return float(c.iloc[-1] / c.iloc[-2] - 1) * 100 if len(c) >= 2 else None
    except Exception:
        return None


# ---------- Logika ----------
def teks_status(s, baru):
    kode = f'<b>{e(s["kode"])}</b>'
    if baru['status'] == 'terbuka':
        return f'{IKON["terbuka"]} {kode} di {rp(baru["harga_masuk"])} · TP {rp(s["tp"])} · SL {rp(s["sl"])}'
    if baru['status'] == 'tidak_terisi':
        return f'{IKON["tidak_terisi"]} {kode}: harga tidak menyentuh zona {rp(s["beli_dari"])}-{rp(s["beli_sampai"])} dalam {rekam.HARI_ISI} hari bursa'
    return (f'{IKON[baru["status"]]} {kode} keluar di {rp(baru["harga_keluar"])} ('
            f'{baru["hasil_pct"]:+.2f}% · {baru["hasil_r"]:+.2f}R)')


def jalankan(mode, db, kirim, harian, terakhir, ihsg, hari_ini=None):
    """Satu putaran tugas. Semua akses luar disuntikkan agar bisa diuji. Hasil: ringkasan dict."""
    hari_ini = hari_ini or rekam.hari_ini()
    aktif = db.sinyal_aktif()
    alert = db.kv_get('alert', []) or []
    alert_hidup = [a for a in alert if a.get('aktif', True) and not a.get('dikirim')]
    terkirim = db.kv_get('notif_terkirim', {}) or {}
    terkirim = {k: v for k, v in terkirim.items() if v >= (rekam.pd.Timestamp(hari_ini) - rekam.pd.Timedelta(days=3)).date().isoformat()}

    kodes = sorted({s['kode'] for s in aktif} | {a['kode'] for a in alert_hidup})
    data_h = harian(sorted({s['kode'] for s in aktif}), '3mo') if aktif else {}
    harga = terakhir(kodes) if kodes else {}

    pesan, tandai, baru_semua = [], [], []
    for s in aktif:
        baru = rekam.evaluasi(s, data_h.get(s['kode']))
        baru_semua.append(baru)
        if baru['status'] != s['status'] and baru['status'] != 'belum_masuk':
            k = f'{s["id"]}|{baru["status"]}'
            if k not in terkirim:
                pesan.append(teks_status(s, baru))
                tandai.append(k)
        if baru['status'] in rekam.AKTIF and s['kode'] in harga:
            p = harga[s['kode']]
            kejadian = []
            if baru['status'] == 'belum_masuk' and p <= float(s['beli_sampai']) * DEKAT_ZONA:
                kejadian.append(('zona', f'📍 <b>{e(s["kode"])}</b> {rp(p)} masuk/dekat zona beli {rp(s["beli_dari"])}-{rp(s["beli_sampai"])}'))
            if baru['status'] == 'terbuka':
                if p <= float(s['sl']) * DEKAT_SL:
                    kejadian.append(('dekatsl', f'⚠️ <b>{e(s["kode"])}</b> {rp(p)} dekat SL {rp(s["sl"])}'))
                if p >= float(s['tp']) * DEKAT_TP:
                    kejadian.append(('dekattp', f'🎯 <b>{e(s["kode"])}</b> {rp(p)} dekat TP {rp(s["tp"])}'))
            for jenis, teks in kejadian:
                k = f'{s["id"]}|{jenis}|{hari_ini}'
                if mode == 'intraday' and k not in terkirim:
                    pesan.append(teks)
                    tandai.append(k)

    # alert harga buatan pengguna
    alert_kirim = []
    if mode == 'intraday':
        for a in alert_hidup:
            p = harga.get(a['kode'])
            if p is None:
                continue
            kena = p >= float(a['harga']) if a.get('op') == '>=' else p <= float(a['harga'])
            if kena:
                arah = 'naik di atas' if a.get('op') == '>=' else 'turun di bawah'
                pesan.append(f'🔔 <b>{e(a["kode"])}</b> {rp(p)} {arah} {rp(a["harga"])}')
                alert_kirim.append(a['id'])
        # IHSG turun tajam
        persen = ihsg()
        k = f'ihsg|{hari_ini}'
        if persen is not None and persen <= IHSG_TURUN and k not in terkirim:
            pesan.append(f'🚨 IHSG turun {persen:.2f}% hari ini. Pertimbangkan memperkecil posisi baru.')
            tandai.append(k)

    # ringkasan harian + validasi skor bola
    ringkasan_skor = None
    if mode == 'harian':
        ringkasan_skor = _perbarui_skor(db, harian, hari_ini)
        peta_baru = {b['id']: b for b in baru_semua}
        semua = [peta_baru.get(x['id'], x) for x in db.sinyal_semua()]
        st = rekam.statistik(semua)
        baris = [f'📊 <b>Ringkasan harian</b> · {e(hari_ini)}',
                 f'Sinyal tercatat {st["total"]} · terbuka {st["terbuka"]} · menunggu masuk {st["belum_masuk"]}']
        if st['semua']:
            t = st['semua']
            baris.append(f'Selesai {t["n"]}: win rate {t["win_rate"]}% · rata-rata {t["rata_r"]:+.2f}R'
                         + (' (sampel masih kecil)' if st['sampel_kecil'] else ''))
        if ringkasan_skor:
            baris.append(f'Skor bola ({ringkasan_skor["n"]} data): ' + ' · '.join(
                f'{k} {v["rata_ret5"]:+.2f}%' for k, v in ringkasan_skor['per_label'].items()))
        pesan = baris + pesan

    berhasil, ket = True, 'tidak ada pesan'
    if pesan:
        berhasil, ket = kirim('\n'.join(pesan))
    if berhasil:
        for k in tandai:
            terkirim[k] = hari_ini
        if aktif:
            db.sinyal_upsert(baru_semua)
        if tandai or alert_kirim:
            db.kv_set('notif_terkirim', terkirim)
        if alert_kirim:
            db.kv_set('alert', [dict(a, dikirim=hari_ini) if a.get('id') in alert_kirim else a for a in alert])
    # Telegram gagal: status TIDAK disimpan, jadi putaran berikutnya mengevaluasi ulang dan mencoba mengirim lagi.
    return {'mode': mode, 'aktif': len(aktif), 'pesan': len(pesan), 'terkirim': berhasil, 'keterangan': ket,
            'skor': ringkasan_skor}


def _perbarui_skor(db, harian, hari_ini):
    """Isi ret5/ret10 untuk snapshot skor yang sudah cukup umur. Hasil: statistik_skor."""
    baris = db.skor_semua()
    batas = (rekam.pd.Timestamp(hari_ini) - rekam.pd.Timedelta(days=6)).date().isoformat()
    perlu = [b for b in baris if b.get('ret10') is None and b['tanggal'] <= batas]
    if perlu:
        data = harian(sorted({b['kode'] for b in perlu}), '3mo')
        baru = [rekam.evaluasi_skor(b, data.get(b['kode'])) for b in perlu]
        db.skor_upsert([b for b, lama in zip(baru, perlu) if (b['ret5'], b['ret10']) != (lama.get('ret5'), lama.get('ret10'))])
        peta = {b['id']: b for b in baru}
        baris = [peta.get(b['id'], b) for b in baris]
    return rekam.statistik_skor(baris)


def main(argv=None):
    mode = (argv or sys.argv)[1] if len(argv or sys.argv) > 1 else 'intraday'
    if mode not in ('intraday', 'harian'):
        print('Mode harus intraday atau harian')
        return 2
    db = penyimpan.dari_env()
    token, chat = os.environ.get('TELEGRAM_BOT_TOKEN'), os.environ.get('TELEGRAM_CHAT_ID')
    if db is None or not token or not chat:
        print('Rahasia belum lengkap (SUPABASE_URL, SUPABASE_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID). Tugas dilewati.')
        return 0
    hasil = jalankan(mode, db, lambda t: notif.kirim(token, chat, t), ambil_harian, ambil_terakhir, ambil_ihsg)
    print({k: v for k, v in hasil.items() if k != 'skor'})
    return 0 if hasil['terkirim'] else 1


if __name__ == '__main__':
    sys.exit(main())
