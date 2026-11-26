"""Catatan kejadian untuk panel Live Feed di tab Terminal (disimpan di sesi, maksimal 120 baris)."""
import streamlit as st

import live


def catat(sumber, teks, level='info'):
    """level: info / ok / warn / err. Panggil hanya dari proses utama Streamlit, bukan dari thread."""
    log = st.session_state.setdefault('jejak', [])
    log.append({'t': live.sekarang().strftime('%H:%M:%S'), 's': str(sumber).upper()[:11], 'x': str(teks)[:160], 'l': level})
    del log[:-120]
