"""Notifikasi Telegram (tanpa Streamlit)."""
import os

import requests

API = os.environ.get('TELEGRAM_API', 'https://api.telegram.org')
BATAS = 3900     # batas Telegram 4096 karakter per pesan


def _potong(teks):
    if len(teks) <= BATAS:
        return [teks]
    bagian, kini = [], ''
    for baris in teks.split('\n'):
        if len(kini) + len(baris) + 1 > BATAS:
            bagian.append(kini)
            kini = ''
        kini += baris + '\n'
    return bagian + ([kini] if kini.strip() else [])


def kirim(token, chat_id, teks):
    """Kirim pesan (HTML). Hasil: (berhasil, keterangan). Token tidak pernah ikut tercetak di keterangan."""
    if not token or not chat_id:
        return False, 'TELEGRAM_BOT_TOKEN atau TELEGRAM_CHAT_ID belum diisi'
    try:
        for bagian in _potong(teks):
            r = requests.post(f'{API}/bot{token}/sendMessage', timeout=20, json={
                'chat_id': chat_id, 'text': bagian, 'parse_mode': 'HTML', 'disable_web_page_preview': True})
            data = r.json() if r.headers.get('content-type', '').startswith('application/json') else {}
            if r.status_code != 200 or not data.get('ok'):
                return False, f'Telegram menolak ({r.status_code}): {str(data.get("description", r.text))[:120]}'
        return True, 'terkirim'
    except requests.RequestException as e:
        return False, 'Gagal menghubungi Telegram: ' + type(e).__name__
