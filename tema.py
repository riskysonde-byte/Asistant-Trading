"""Tampilan aplikasi: tema gelap hijau ala aplikasi saham (CSS, bar pasar, watchlist)."""
import html

import streamlit as st

HIJAU = '#00AB6B'
MERAH = '#E5484D'
ABU = '#8B93A1'

CSS = """
<style>
[data-testid="stMainBlockContainer"]{max-width:960px;padding:4rem 1rem 5rem}
footer{visibility:hidden}
h1,h2,h3,h4{letter-spacing:-.01em}

/* tab: menempel di atas, hijau saat aktif */
[data-testid="stTabs"] [role="tablist"]{position:sticky;top:3.4rem;z-index:50;background:#0F1115;
  border-bottom:1px solid rgba(128,128,128,.22);gap:2px;overflow-x:auto;scrollbar-width:none}
[data-testid="stTabs"] [role="tablist"]::-webkit-scrollbar{display:none}
button[role="tab"]{font-weight:600;font-size:.88rem;padding:.7rem .85rem;color:#8B93A1;white-space:nowrap}
button[role="tab"][aria-selected="true"]{color:#00AB6B}

/* kartu */
[data-testid="stMetric"]{background:rgba(128,128,128,.07);border:1px solid rgba(128,128,128,.18);
  border-radius:14px;padding:.7rem .9rem}
[data-testid="stMetricValue"]{font-variant-numeric:tabular-nums}
[data-testid="stExpander"],[data-testid="stVerticalBlockBorderWrapper"]{border-radius:14px!important}
[data-testid="stExpander"]{border:1px solid rgba(128,128,128,.2)!important;background:rgba(128,128,128,.05)}
[data-testid="stAlert"]{border-radius:12px}
[data-testid="stDataFrame"]{border-radius:12px;overflow:hidden}
[data-testid="stChatMessage"]{border-radius:14px;background:rgba(128,128,128,.07)}
[data-baseweb="input"],[data-baseweb="textarea"],[data-baseweb="select"]>div{border-radius:10px!important}
[data-testid^="stBaseButton"]{border-radius:10px;font-weight:600}
[data-testid="stBaseButton-primary"],[data-testid="stBaseButton-primaryFormSubmit"]{background:#00AB6B;border-color:#00AB6B;color:#fff}
[data-testid="stProgress"] [role="progressbar"]>div{background:#00AB6B}

/* header dan bar pasar */
.topbar{display:flex;align-items:center;justify-content:space-between;gap:.6rem;margin:.1rem 0 .7rem}
.brand{display:flex;gap:.65rem;align-items:center;min-width:0}
.logo{width:38px;height:38px;border-radius:11px;background:linear-gradient(135deg,#00AB6B,#0A7A4F);
  display:grid;place-items:center;color:#fff;font-weight:800;font-size:.95rem;flex:0 0 auto}
.brand b{font-size:1.08rem;display:block;line-height:1.15}
.brand small{color:#8B93A1;font-size:.72rem;display:block}
.st-chip{font-size:.74rem;padding:.28rem .65rem;border-radius:99px;background:rgba(0,171,107,.15);
  color:#00AB6B;font-weight:700;white-space:nowrap}
.st-chip.off{background:rgba(128,128,128,.2);color:#8B93A1}
.strip{display:flex;gap:.5rem;overflow-x:auto;padding:.1rem 0 .8rem;scrollbar-width:none}
.strip::-webkit-scrollbar{display:none}
.mk{flex:0 0 auto;min-width:108px;border:1px solid rgba(128,128,128,.2);background:rgba(128,128,128,.06);
  border-radius:12px;padding:.4rem .7rem}
.mk small{display:block;color:#8B93A1;font-size:.68rem}
.mk b{font-size:.92rem;font-variant-numeric:tabular-nums}
.mk span{font-size:.72rem;font-weight:700;margin-left:.35rem}
.up{color:#00AB6B}.dn{color:#E5484D}.flat{color:#8B93A1}

/* watchlist */
.wl{border:1px solid rgba(128,128,128,.2);border-radius:16px;overflow:hidden;margin:.3rem 0 .9rem}
.wl-row{display:grid;grid-template-columns:minmax(0,1fr) 84px auto;gap:.7rem;align-items:center;
  padding:.7rem .95rem;border-bottom:1px solid rgba(128,128,128,.14)}
.wl-row:last-child{border-bottom:0}
.wl-row svg{width:100%;height:30px;display:block}
.wl-row.sel{background:rgba(0,171,107,.08)}
.wl-l b{font-size:1.02rem}
.wl-l span{display:block;color:#8B93A1;font-size:.72rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.wl-r{text-align:right}
.wl-r b{display:block;font-size:1.02rem;font-variant-numeric:tabular-nums}
.pill{display:inline-block;min-width:66px;text-align:center;padding:.1rem .45rem;border-radius:7px;
  font-size:.78rem;font-weight:700;margin-top:.15rem;font-variant-numeric:tabular-nums}
.pill.up{background:rgba(0,171,107,.16)}.pill.dn{background:rgba(229,72,77,.16)}
.pill.flat{background:rgba(128,128,128,.2)}
/* kotak statistik 2x2 */
.sg{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.55rem;margin:.2rem 0 .9rem}
.sg>div{background:rgba(128,128,128,.07);border:1px solid rgba(128,128,128,.18);border-radius:14px;padding:.6rem .85rem}
.sg small{display:block;color:#8B93A1;font-size:.72rem}
.sg b{font-size:1.15rem;font-variant-numeric:tabular-nums}
.sg .pill{margin:0 0 0 .4rem;min-width:0;font-size:.72rem}
@media (max-width:520px){.sg{grid-template-columns:repeat(2,1fr)}.wl-row{grid-template-columns:minmax(0,1fr) 56px auto;gap:.5rem;padding:.65rem .75rem}.pill{min-width:60px}}
</style>
"""


def terapkan():
    st.markdown(CSS, unsafe_allow_html=True)


def _kelas(v):
    return 'up' if v > 0 else 'dn' if v < 0 else 'flat'


def angka(v, nd=0):
    return f'{v:,.{nd}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def persen(v):
    return f'{v:+.2f}%'.replace('.', ',')


def header(buka, keterangan):
    chip = f'<span class="st-chip {"" if buka else "off"}">{"●" if buka else "○"} {html.escape(keterangan)}</span>'
    st.markdown(f'<div class="topbar"><div class="brand"><div class="logo">AT</div><div><b>Asisten Trading</b>'
                f'<small>IDX · data Yahoo tertunda 10-15 menit</small></div></div>{chip}</div>', unsafe_allow_html=True)


def bar_pasar(data):
    """Deretan chip indeks, kurs, dan komoditas (bisa digeser ke samping)."""
    if not data:
        return
    chips = []
    for x in data:
        nd = 0 if x['label'] == 'USD/IDR' else 2
        chips.append(f'<div class="mk"><small>{html.escape(x["label"])}</small><b>{angka(x["terakhir"], nd)}</b>'
                     f'<span class="{_kelas(x["ubah_pct"])}">{persen(x["ubah_pct"])}</span></div>')
    st.markdown('<div class="strip">' + ''.join(chips) + '</div>', unsafe_allow_html=True)


def sparkline(nilai, prev, w=84, h=30):
    """Garis mini harga hari ini (SVG), hijau jika di atas penutupan kemarin, merah jika di bawah."""
    nilai = [float(v) for v in nilai]
    if len(nilai) < 2:
        return ''
    langkah = max(1, len(nilai) // 40)
    nilai = nilai[::langkah] + ([nilai[-1]] if (len(nilai) - 1) % langkah else [])
    lo, hi = min(nilai + [prev]), max(nilai + [prev])
    rentang = (hi - lo) or 1
    pts = ' '.join(f'{i * (w - 2) / (len(nilai) - 1) + 1:.1f},{h - 2 - (v - lo) / rentang * (h - 4):.1f}'
                   for i, v in enumerate(nilai))
    y0 = h - 2 - (prev - lo) / rentang * (h - 4)
    warna = HIJAU if nilai[-1] >= prev else MERAH
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}"><line x1="0" x2="{w}" y1="{y0:.1f}" y2="{y0:.1f}" '
            f'stroke="{ABU}" stroke-opacity=".5" stroke-dasharray="2 3"/><polyline points="{pts}" fill="none" '
            f'stroke="{warna}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/></svg>')


def watchlist(data, nama, terpilih=None):
    """Baris watchlist: kode + nama, sparkline, harga, dan label persen berwarna."""
    baris = []
    for k, x in data.items():
        spark = sparkline(x['bar']['Close'].tolist(), x['prev'])
        baris.append(
            f'<div class="wl-row{" sel" if k == terpilih else ""}">'
            f'<div class="wl-l"><b>{html.escape(k)}</b><span>{html.escape(nama.get(k, ""))}</span></div>'
            f'<div>{spark}</div>'
            f'<div class="wl-r"><b>{angka(x["harga"])}</b>'
            f'<span class="pill {_kelas(x["ubah_pct"])}">{persen(x["ubah_pct"])}</span></div></div>')
    st.markdown('<div class="wl">' + ''.join(baris) + '</div>', unsafe_allow_html=True)


def statistik(kode, x):
    """Kotak ringkas: harga + persen, high/low, volume, bar terakhir."""
    kartu = [
        (kode, f'{angka(x["harga"])}<span class="pill {_kelas(x["ubah_pct"])}">{persen(x["ubah_pct"])}</span>'),
        ('High / Low', f'{angka(x["high"])} / {angka(x["low"])}'),
        ('Volume', f'{angka(x["volume"] / 100)} lot'),
        ('Bar terakhir', f'{x["waktu"]:%d-%m %H:%M} WIB'),
    ]
    st.markdown('<div class="sg">' + ''.join(f'<div><small>{html.escape(a)}</small><b>{b}</b></div>' for a, b in kartu)
                + '</div>', unsafe_allow_html=True)
