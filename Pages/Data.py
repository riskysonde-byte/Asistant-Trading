"""Halaman data: tarik data Yahoo, hasilnya satu teks siap salin ke Claude."""
import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(page_title='Data untuk Claude', layout='centered')


def rp(n):
    return f'{n:,.0f}'.replace(',', '.')


def ambil(kode):
    df = yf.download(kode + '.JK', period='1y', auto_adjust=False, progress=False)
    if df is None or df.empty:
        raise ValueError('Data ' + kode + ' tidak ditemukan')
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    return df


def fundamental(kode):
    try:
        info = yf.Ticker(kode + '.JK').info or {}
    except Exception:
        return {}
    ks = ['longName', 'sector', 'marketCap', 'trailingPE', 'priceToBook', 'returnOnEquity',
          'dividendYield', 'trailingEps', 'fiftyTwoWeekHigh', 'fiftyTwoWeekLow']
    return {k: info[k] for k in ks if info.get(k) is not None}


def berita(kode):
    try:
        items = yf.Ticker(kode + '.JK').news or []
    except Exception:
        return []
    out = []
    for it in items[:6]:
        c = it.get('content') if isinstance(it.get('content'), dict) else it
        t = c.get('title') or it.get('title')
        if t:
            out.append(str(t) + ' (' + str(c.get('pubDate') or '')[:10] + ')')
    return out


def susun(kode, df, fund, news):
    d = df.copy()
    d['MA20'] = d['Close'].rolling(20).mean()
    d['MA50'] = d['Close'].rolling(50).mean()
    d['MA200'] = d['Close'].rolling(200).mean()
    d['VOLMA'] = d['Volume'].rolling(20).mean()
    delta = d['Close'].diff()
    naik = delta.clip(lower=0).rolling(14).mean()
    turun = (-delta.clip(upper=0)).rolling(14).mean()
    d['RSI'] = 100 - 100 / (1 + naik / turun)
    macd = d['Close'].ewm(span=12).mean() - d['Close'].ewm(span=26).mean()
    sig = macd.ewm(span=9).mean()
    tr = pd.concat([d['High'] - d['Low'], (d['High'] - d['Close'].shift()).abs(),
                    (d['Low'] - d['Close'].shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    a = d.iloc[-1]
    h5 = (a['Close'] / d['Close'].iloc[-6] - 1) * 100 if len(d) > 6 else float('nan')
    L = []
    L.append(f'DATA OTOMATIS {kode} (Yahoo Finance, tunda sekitar 10 menit, tidak resmi)')
    L.append(f'Harga terakhir: Rp{rp(a["Close"])} (bar {d.index[-1]:%d-%m-%Y})')
    L.append(f'Perubahan 5 hari: {h5:.1f}%'.replace('.', ','))
    L.append(f'MA20 {rp(a["MA20"])} | MA50 {rp(a["MA50"])} | MA200 ' + (rp(a['MA200']) if pd.notna(a['MA200']) else 'n/a'))
    L.append(f'RSI14 {a["RSI"]:.1f} | MACD {macd.iloc[-1]:.1f} vs sinyal {sig.iloc[-1]:.1f} | ATR14 {rp(atr)}'.replace('.', ','))
    L.append(f'Volume {a["Volume"] / a["VOLMA"]:.1f}x rata-rata 20 hari'.replace('.', ','))
    L.append(f'Rentang 20 hari: low {rp(d["Low"].tail(20).min())} - high {rp(d["High"].tail(20).max())}')
    L.append(f'Rentang 60 hari: low {rp(d["Low"].tail(60).min())} - high {rp(d["High"].tail(60).max())}')
    if fund:
        L.append('Fundamental: ' + ', '.join(f'{k}={v}' for k, v in fund.items()))
    L.append('Berita: ' + (' | '.join(news) if news else 'tidak ada'))
    return '\n'.join(L)


if __name__ == '__main__' or True:
    st.title('Data untuk Claude')
    st.caption('Tarik data Yahoo, lalu salin teksnya ke tab Analisis di halaman Claude (kolom Data tambahan).')
    kodes = st.text_input('Kode saham (boleh lebih dari satu, pisahkan koma)', 'BBCA')
    if st.button('Ambil data'):
        for kode in [k.strip().upper() for k in kodes.split(',') if k.strip()]:
            try:
                teks = susun(kode, ambil(kode), fundamental(kode), berita(kode))
                st.code(teks, language=None)
            except Exception as e:
                st.error(kode + ': ' + str(e)[:150])
        st.info('Tekan ikon salin di pojok kotak, lalu tempel di Claude.')
