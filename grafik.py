"""Grafik candlestick untuk tab Live: volume, MA, VWAP, dan garis penutupan kemarin."""
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

NAIK = '#16a34a'
TURUN = '#dc2626'
BIRU = '#3b82f6'
UNGU = '#a855f7'
ORANYE = '#f59e0b'
ABU = '#94a3b8'


def resample_ohlcv(d, menit):
    """Gabungkan bar 1 menit menjadi bar 5/15/... menit. Menit 1 = apa adanya."""
    if menit <= 1:
        return d
    r = d.resample(f'{menit}min').agg({'Open': 'first', 'High': 'max', 'Low': 'min',
                                       'Close': 'last', 'Volume': 'sum'})
    return r.dropna(subset=['Close'])


def vwap(d):
    """VWAP per hari perdagangan (reset tiap hari)."""
    tipikal = (d['High'] + d['Low'] + d['Close']) / 3
    hari = d.index.date
    pv = (tipikal * d['Volume']).groupby(hari).cumsum()
    v = d['Volume'].groupby(hari).cumsum()
    return pv / v.where(v > 0)


def _hari_kosong(idx):
    """Tanggal kerja yang tidak ada datanya (libur bursa), supaya tidak jadi celah kosong di grafik."""
    if len(idx) < 2:
        return []
    ada = set(pd.DatetimeIndex(idx).normalize())
    semua = pd.bdate_range(min(ada), max(ada))
    return [t.strftime('%Y-%m-%d') for t in semua if t not in ada]


def candle(d, kode, prev_close=None, intraday=True, ma=(20,), tampil_vwap=True, tinggi=520, kunci_ui='',
           mulai=None, tampil_n=None):
    """d: DataFrame Open/High/Low/Close/Volume (beri data lengkap). Hasil: figure Plotly.

    MA dan VWAP dihitung dari seluruh data, baru dipotong untuk tampilan: dari tanggal `mulai`
    atau `tampil_n` bar terakhir, supaya garisnya sudah terbentuk sejak bar pertama yang tampak."""
    d = d.copy()
    if d.index.tz is not None:
        d.index = d.index.tz_localize(None)
    d['_vwap'] = vwap(d) if (tampil_vwap and intraday) else float('nan')
    for w in ma:
        d[f'_ma{w}'] = d['Close'].rolling(w).mean()
    if mulai is not None:
        d = d[d.index >= pd.Timestamp(mulai)]
    if tampil_n:
        d = d.tail(tampil_n)
    x = d.index
    naik = d['Close'] >= d['Open']

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.76, 0.24], vertical_spacing=0.025)
    fig.add_trace(go.Candlestick(
        x=x, open=d['Open'], high=d['High'], low=d['Low'], close=d['Close'], name=kode, showlegend=False,
        increasing=dict(line=dict(color=NAIK, width=1), fillcolor=NAIK),
        decreasing=dict(line=dict(color=TURUN, width=1), fillcolor=TURUN)), row=1, col=1)

    warna_ma = [BIRU, ORANYE, UNGU]
    for w, wr in zip(ma, warna_ma):
        if d[f'_ma{w}'].notna().any():
            fig.add_trace(go.Scatter(x=x, y=d[f'_ma{w}'], name=f'MA{w}', mode='lines',
                                     line=dict(color=wr, width=1.4), hoverinfo='skip'), row=1, col=1)
    if d['_vwap'].notna().any():
        fig.add_trace(go.Scatter(x=x, y=d['_vwap'], name='VWAP', mode='lines',
                                 line=dict(color=ABU, width=1.4, dash='dash'), hoverinfo='skip'), row=1, col=1)
    if prev_close:
        fig.add_trace(go.Scatter(x=[x[0], x[-1]], y=[prev_close, prev_close], mode='lines',
                                 name=f'Tutup kemarin {prev_close:,.0f}'.replace(',', '.'),
                                 line=dict(color=ABU, width=1, dash='dot'), hoverinfo='skip'), row=1, col=1)

    fig.add_trace(go.Bar(x=x, y=d['Volume'] / 100, name='Volume (lot)', showlegend=False,
                         marker=dict(color=[NAIK if n else TURUN for n in naik], opacity=0.55, line=dict(width=0))),
                  row=2, col=1)

    terakhir = float(d['Close'].iloc[-1])
    fig.add_annotation(x=x[-1], y=terakhir, xref='x', yref='y', text=f' {terakhir:,.0f} ', showarrow=False,
                       xanchor='left', font=dict(color='white', size=11),
                       bgcolor=NAIK if naik.iloc[-1] else TURUN, borderpad=2)

    if intraday:
        pecah = [dict(bounds=['sat', 'mon']), dict(bounds=[16, 9], pattern='hour')]
    else:
        pecah = [dict(bounds=['sat', 'mon'])]
        kosong = _hari_kosong(x)
        if kosong:
            pecah.append(dict(values=kosong))
    fig.update_xaxes(rangebreaks=pecah, rangeslider_visible=False, showgrid=False,
                     showspikes=True, spikemode='across', spikethickness=1, spikedash='dot', spikecolor=ABU)
    fig.update_yaxes(tickformat=',.0f', side='right', row=1, col=1)
    fig.update_yaxes(tickformat=',.0f', side='right', showgrid=False, row=2, col=1)
    fig.update_layout(
        height=tinggi, margin=dict(l=8, r=8, t=28, b=8), hovermode='x unified', dragmode='pan',
        separators=',.', uirevision=kunci_ui or kode,
        legend=dict(orientation='h', yanchor='bottom', y=1.0, xanchor='left', x=0, font=dict(size=11)),
        xaxis2=dict(tickformat='%H:%M' if intraday else '%d %b'),
        bargap=0.15)
    return fig


CONFIG = {'displaylogo': False, 'scrollZoom': True,
          'modeBarButtonsToRemove': ['lasso2d', 'select2d', 'autoScale2d']}
