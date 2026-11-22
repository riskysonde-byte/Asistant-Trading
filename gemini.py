"""Pemanggil Gemini: teks, gambar, dan pencarian web (Google Search)."""
import base64
import json
import time

import requests
import streamlit as st

from agents import PROMPTS

MODEL_DEFAULT = 'gemini-2.5-flash'   # bisa diganti lewat Secrets: GEMINI_MODEL


def rahasia(nama):
    try:
        return st.secrets[nama]
    except Exception:
        return None


def kunci():
    k = rahasia('GEMINI_API_KEY')
    return str(k).strip() if k else None


def model_ai():
    return str(rahasia('GEMINI_MODEL') or MODEL_DEFAULT).strip()


def blok_gambar(files):
    # Ubah screenshot yang diunggah menjadi bagian gambar untuk Gemini.
    blok = []
    for f in files or []:
        tipe = f.type if f.type in ('image/png', 'image/jpeg', 'image/webp') else 'image/png'
        blok.append({'inline_data': {'mime_type': tipe,
                                     'data': base64.b64encode(f.getvalue()).decode()}})
    return blok


def _sumber_web(data):
    """Sumber asli dari Google Search (bukan tulisan AI): [{'judul', 'url'}]."""
    try:
        potong = data['candidates'][0].get('groundingMetadata', {}).get('groundingChunks', [])
    except Exception:
        return []
    hasil, lihat = [], set()
    for c in potong:
        w = c.get('web') or {}
        u = w.get('uri')
        if u and u not in lihat:
            lihat.add(u)
            hasil.append({'judul': w.get('title') or u, 'url': u})
    return hasil


def jalankan(nama, payload, max_tokens=1200, gambar=None, web=False, sumber=False):
    """Panggil satu agen. web=True memakai Google Search. sumber=True mengembalikan (teks, daftar_sumber)."""
    k = kunci()
    if not k:
        raise RuntimeError('GEMINI_API_KEY belum diisi di Secrets')
    bagian = list(gambar or [])
    bagian.append({'text': json.dumps(payload, ensure_ascii=False, default=str)})
    body = {
        'system_instruction': {'parts': [{'text': PROMPTS[nama]}]},
        'contents': [{'role': 'user', 'parts': bagian}],
        'generationConfig': {'maxOutputTokens': max(max_tokens, 2000), 'temperature': 0.3},
    }
    if web:
        body['tools'] = [{'google_search': {}}]
    url = 'https://generativelanguage.googleapis.com/v1beta/models/' + model_ai() + ':generateContent'
    r = None
    for percobaan in range(3):
        r = requests.post(url, headers={'x-goog-api-key': k}, json=body, timeout=180 if web else 90)
        if r.status_code in (429, 500, 503) and percobaan < 2:
            time.sleep(4 * (percobaan + 1))
            continue
        break
    if r.status_code != 200:
        raise RuntimeError('Gemini ' + str(r.status_code) + ': ' + r.text[:200])
    data = r.json()
    try:
        teks = ''.join(p.get('text', '') for p in data['candidates'][0]['content']['parts'])
    except Exception:
        raise RuntimeError('Jawaban Gemini kosong atau diblokir: ' + json.dumps(data)[:200])
    return (teks, _sumber_web(data)) if sumber else teks
