"""Data intraday (per menit) dari Yahoo Finance untuk tampilan live.

Yahoo untuk saham IDX tertunda sekitar 10-15 menit dan tidak resmi.
"""
import datetime as dt

import pandas as pd
import streamlit as st
import yfinance as yf

WIB = dt.timezone(dt.timedelta(hours=7), 'WIB')


def sekarang():
    return dt.datetime.now(WIB)


def status_bursa(now=None):
    """(buka?, keterangan) menurut jam perdagangan BEI. Hari libur bursa tidak dihitung."""
    now = now or sekarang()
    if now.weekday() >= 5:
        return False, 'Bursa tutup (akhir pekan)'
    t = now.time()
    jumat = now.weekday() == 4
    akhir_sesi1 = dt.time(11, 30) if jumat else dt.time(12, 0)
    awal_sesi2 = dt.time(14, 0) if jumat else dt.time(13, 30)
    if dt.time(8, 45) <= t < dt.time(9, 0):
        return True, 'Pra-pembukaan'
    if dt.time(9, 0) <= t < akhir_sesi1:
        return True, 'Sesi 1'
    if akhir_sesi1 <= t < awal_sesi2:
        return False, 'Istirahat siang'
    if awal_sesi2 <= t < dt.time(15, 50):
        return True, 'Sesi 2'
    if dt.time(15, 50) <= t < dt.time(16, 0):
        return True, 'Pra-penutupan'
    return False, 'Bursa tutup'


@st.cache_data(ttl=30, show_spinner=False)
def get_intraday(kodes, interval='1m'):
    """Bar per menit 5 hari terakhir untuk banyak saham sekaligus (satu permintaan).

    Hasil: {kode: DataFrame Open/High/Low/Close/Volume, index jam WIB}.
    """
    kodes = tuple(kodes)
    if not kodes:
        return {}
    tickers = [k + '.JK' for k in kodes]
    df = yf.download(tickers, period='5d', interval=interval, auto_adjust=False,
                     progress=False, group_by='ticker', threads=True)
    hasil = {}
    if df is None or df.empty:
        return hasil
    for k, t in zip(kodes, tickers):
        if isinstance(df.columns, pd.MultiIndex):
            if t not in df.columns.get_level_values(0):
                continue
            d = df[t]
        else:
            d = df
        d = d.dropna(subset=['Close'])
        if d.empty:
            continue
        d = d.copy()
        if d.index.tz is None:
            d.index = d.index.tz_localize('UTC')
        d.index = d.index.tz_convert('Asia/Jakarta')
        hasil[k] = d
    return hasil


def ringkas(d):
    """Ringkasan hari perdagangan terakhir dari bar per menit."""
    tanggal = d.index.date
    hari_ini = tanggal[-1]
    h = d[tanggal == hari_ini]
    sebelum = d[tanggal < hari_ini]
    harga = float(h['Close'].iloc[-1])
    prev = float(sebelum['Close'].iloc[-1]) if not sebelum.empty else float(h['Open'].iloc[0])
    waktu = h.index[-1].to_pydatetime()
    return {
        'harga': harga,
        'prev': prev,
        'ubah': harga - prev,
        'ubah_pct': (harga / prev - 1) * 100 if prev else 0.0,
        'open': float(h['Open'].iloc[0]),
        'high': float(h['High'].max()),
        'low': float(h['Low'].min()),
        'volume': float(h['Volume'].sum()),
        'tanggal': hari_ini,
        'waktu': waktu,
        'telat_menit': max(0, int((sekarang() - waktu).total_seconds() // 60)),
        'bar': h,
    }


def harga_live(kodes):
    """{kode: ringkasan} untuk saham yang datanya berhasil diambil. Gagal = dict kosong."""
    try:
        data = get_intraday(tuple(kodes))
    except Exception:
        return {}
    out = {}
    for k, d in data.items():
        try:
            out[k] = ringkas(d)
        except Exception:
            continue
    return out


def sambung_live(df_harian, live):
    """Timpa/tambah bar harian terakhir dengan data per menit hari ini,
    supaya indikator (MA, RSI, MACD, volume) memakai harga terkini."""
    if not live:
        return df_harian
    d = df_harian.copy()
    tgl = pd.Timestamp(live['tanggal'])
    if d.index.tz is not None:
        tgl = tgl.tz_localize(d.index.tz)
    if len(d) and d.index[-1].date() == live['tanggal']:
        d.loc[d.index[-1], ['Close', 'High', 'Low', 'Volume']] = [
            live['harga'], max(float(d['High'].iloc[-1]), live['high']),
            min(float(d['Low'].iloc[-1]), live['low']), max(float(d['Volume'].iloc[-1]), live['volume'])]
        if 'Adj Close' in d.columns:
            d.loc[d.index[-1], 'Adj Close'] = live['harga']
    elif len(d) == 0 or d.index[-1].date() < live['tanggal']:
        baris = {'Open': live['open'], 'High': live['high'], 'Low': live['low'],
                 'Close': live['harga'], 'Volume': live['volume']}
        if 'Adj Close' in d.columns:
            baris['Adj Close'] = live['harga']
        d.loc[tgl] = pd.Series(baris)
    return d
