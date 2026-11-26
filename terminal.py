"""Tab Terminal: dashboard padat ala terminal trading (status, bola agen 3D, heatmap, grafik mini, live feed)."""
import html
import json

import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

import grafik
import live
import simulasi as sm
from fitur_web import pasar_hari_ini
from kantor import stat_jurnal
from tema import angka, persen
from tim_agen import TIM

AGEN = [n for n, _ in TIM]
WARNA_STATUS = {'aktif': '#00FF9C', 'lewat': '#6B7280', 'galat': '#FF4D4F', 'idle': '#22D3EE'}
KET_STATUS = {'aktif': 'AKTIF', 'lewat': 'DILEWATI', 'galat': 'GALAT', 'idle': 'SIAGA'}
HARI = ['SEN', 'SEL', 'RAB', 'KAM', 'JUM', 'SAB', 'MIN']

CSS = """
<style>
.tm-bar{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
  font-size:.74rem;border:1px solid rgba(0,255,156,.28);background:rgba(0,255,156,.04);border-radius:10px;padding:.5rem .7rem;margin-bottom:.7rem}
.tm-bar b{color:#00FF9C}.tm-bar span{color:#8B93A1}.tm-bar .sep{opacity:.3}
.tm-h{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.7rem;letter-spacing:.14em;text-transform:uppercase;
  color:#22D3EE;margin:.2rem 0 .35rem;display:flex;justify-content:space-between}
.tm-h i{font-style:normal;color:#8B93A1;letter-spacing:.04em}
.tm-box{border:1px solid rgba(34,211,238,.22);background:rgba(8,20,24,.55);border-radius:10px;padding:.55rem .7rem;
  box-shadow:inset 0 0 24px rgba(0,255,156,.04)}
.tm-feed{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.72rem;line-height:1.55;max-height:260px;overflow-y:auto}
.tm-feed div{white-space:pre-wrap;word-break:break-word}
.tm-feed .t{color:#6B7280}.tm-feed .s{color:#22D3EE;font-weight:700}
.tm-feed .ok{color:#00FF9C}.tm-feed .warn{color:#F5B342}.tm-feed .err{color:#FF4D4F}.tm-feed .info{color:#C9D1D9}
.tm-tab{width:100%;border-collapse:collapse;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.74rem}
.tm-tab th{color:#8B93A1;font-weight:500;text-align:left;padding:.15rem .3rem;border-bottom:1px solid rgba(128,128,128,.2)}
.tm-tab td{padding:.22rem .3rem;border-bottom:1px solid rgba(128,128,128,.1)}
.tm-b{padding:.05rem .4rem;border-radius:5px;font-weight:700;font-size:.7rem}
.tm-b.BELI{background:rgba(0,255,156,.16);color:#00FF9C}.tm-b.TUNGGU{background:rgba(245,179,66,.16);color:#F5B342}
.tm-b.SKIP{background:rgba(255,77,79,.16);color:#FF4D4F}
.tm-w{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:.55rem;margin-top:.2rem}
.tm-w>div{border:1px solid rgba(34,211,238,.22);background:rgba(8,20,24,.55);border-radius:10px;padding:.55rem .75rem}
.tm-w small{display:block;color:#8B93A1;font-family:ui-monospace,Menlo,monospace;font-size:.66rem;letter-spacing:.08em;text-transform:uppercase}
.tm-w b{font-family:ui-monospace,Menlo,monospace;font-size:1.15rem}
.tm-lg{display:flex;gap:.8rem;flex-wrap:wrap;font-family:ui-monospace,Menlo,monospace;font-size:.68rem;color:#8B93A1;margin-top:.2rem}
.tm-lg i{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:.3rem}
</style>
"""

BOLA = """
<canvas id="c" style="width:100%;height:330px;display:block"></canvas>
<script>
const AG = __AGEN__;
const WARNA = __WARNA__;
const cv = document.getElementById('c'), ctx = cv.getContext('2d');
let W = 0, H = 0; const DPR = window.devicePixelRatio || 1;
function fit(){ W = cv.clientWidth; H = cv.clientHeight; cv.width = W*DPR; cv.height = H*DPR; ctx.setTransform(DPR,0,0,DPR,0,0); }
fit(); addEventListener('resize', fit);
const N = 850, P = [], GA = Math.PI*(3-Math.sqrt(5));
for (let i = 0; i < N; i++){ const y = 1-2*(i+.5)/N, r = Math.sqrt(1-y*y), th = GA*i; P.push([Math.cos(th)*r, y, Math.sin(th)*r, Math.random()*6.28]); }
const NODE = AG.map((a,i) => { const y = 1-2*(i+.5)/AG.length, r = Math.sqrt(1-y*y), th = GA*i*1.7; return {a, p:[Math.cos(th)*r, y, Math.sin(th)*r]}; });
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
let ang = 0;
function rot(p, ay, ax){ const x = p[0]*Math.cos(ay)+p[2]*Math.sin(ay), z = -p[0]*Math.sin(ay)+p[2]*Math.cos(ay), y = p[1];
  return [x, y*Math.cos(ax)-z*Math.sin(ax), y*Math.sin(ax)+z*Math.cos(ax)]; }
function proj(q, R){ const s = 3.2/(3.2+q[2]*0.9); return [W/2+q[0]*R*s, H/2+q[1]*R*s, s]; }
function frame(t){
  ctx.clearRect(0,0,W,H); const R = Math.min(W,H)*0.36;
  const g = ctx.createRadialGradient(W/2,H/2,R*0.1,W/2,H/2,R*1.3); g.addColorStop(0,'rgba(0,255,156,0.08)'); g.addColorStop(1,'rgba(0,0,0,0)');
  ctx.fillStyle = g; ctx.fillRect(0,0,W,H);
  const ay = reduce ? 0.6 : ang, ax = 0.35;
  for (const p of P){ const q = rot(p,ay,ax), s = proj(q,R), d = (q[2]+1)/2, tw = 0.6+0.4*Math.sin(t/700+p[3]);
    ctx.fillStyle = 'rgba(120,255,214,'+(0.12+0.55*d*tw).toFixed(3)+')'; const z = 1.2*s[2]+0.3; ctx.fillRect(s[0],s[1],z,z); }
  const pts = NODE.map(n => ({n, q: rot(n.p,ay,ax)}));
  ctx.lineWidth = 0.7;
  for (let i = 0; i < pts.length; i++) for (let j = i+1; j < pts.length; j++){
    if (pts[i].n.a.s === 'aktif' && pts[j].n.a.s === 'aktif'){
      const A = proj(pts[i].q,R*1.12), B = proj(pts[j].q,R*1.12), d = (pts[i].q[2]+pts[j].q[2]+2)/4;
      ctx.strokeStyle = 'rgba(0,255,156,'+(0.05+0.2*d).toFixed(3)+')'; ctx.beginPath(); ctx.moveTo(A[0],A[1]); ctx.lineTo(B[0],B[1]); ctx.stroke(); } }
  pts.sort((a,b) => a.q[2]-b.q[2]);
  for (const {n,q} of pts){
    const s = proj(q,R*1.12), col = WARNA[n.a.s] || WARNA.idle, front = q[2] > -0.15;
    const pulse = n.a.s === 'aktif' ? 1+0.35*Math.sin(t/260+n.p[1]*5) : 1;
    ctx.globalAlpha = front ? 1 : 0.35; ctx.shadowColor = col; ctx.shadowBlur = n.a.s === 'aktif' ? 14 : 6; ctx.fillStyle = col;
    ctx.beginPath(); ctx.arc(s[0],s[1],4.2*s[2]*pulse,0,6.283); ctx.fill(); ctx.shadowBlur = 0;
    if (front){ ctx.font = '600 10px ui-monospace,Menlo,monospace'; ctx.textAlign = s[0] > W/2 ? 'left' : 'right';
      ctx.fillText(n.a.n, s[0]+(s[0] > W/2 ? 9 : -9), s[1]+3); }
    ctx.globalAlpha = 1; }
  if (!reduce){ ang += 0.0035; requestAnimationFrame(frame); }
}
requestAnimationFrame(frame);
</script>
"""


def status_agen():
    """Status tiap agen dari hasil Kantor Agen terakhir: aktif, lewat, galat, atau idle (siaga)."""
    h = st.session_state.get('kantor')
    if not h:
        return {n: 'idle' for n in AGEN}
    s = {}
    for n in AGEN:
        if n in h['galat']:
            s[n] = 'galat'
        elif n in h['dilewati']:
            s[n] = 'lewat'
        elif n == 'PELATIH':
            s[n] = 'aktif' if st.session_state.get('pelatih') else 'idle'
        else:
            s[n] = 'aktif'
    return s


def bar_status():
    now = live.sekarang()
    buka, ket = live.status_bursa(now)
    p = pasar_hari_ini()
    pasar = (f'<b>{p["keputusan"]}</b> <span>skor {p["skor"]}</span>' if p else '<span>belum dicek</span>')
    h = st.session_state.get('kantor')
    kantor = f'<b>{h["waktu"]:%H:%M}</b>' if h else '<span>belum jalan</span>'
    st.markdown(
        f'<div class="tm-bar"><span>{HARI[now.weekday()]} {now:%d-%m-%Y}</span><b>{now:%H:%M:%S} WIB</b><span class="sep">|</span>'
        f'<b style="color:{"#00FF9C" if buka else "#8B93A1"}">{html.escape(ket.upper())}</b><span class="sep">|</span>'
        f'<span>PASAR HARI INI</span> {pasar}<span class="sep">|</span><span>KANTOR AGEN</span> {kantor}<span class="sep">|</span>'
        f'<span>DATA YAHOO ± 10-15 MNT</span></div>', unsafe_allow_html=True)


def panel_judul(judul, kanan=''):
    st.markdown(f'<div class="tm-h"><span>▍{html.escape(judul)}</span><i>{html.escape(kanan)}</i></div>', unsafe_allow_html=True)


def bola_agen():
    status = status_agen()
    agen = [{'n': n, 's': status[n]} for n in AGEN]
    components.html(BOLA.replace('__AGEN__', json.dumps(agen)).replace('__WARNA__', json.dumps(WARNA_STATUS)), height=335)
    hitung = {k: sum(1 for v in status.values() if v == k) for k in WARNA_STATUS}
    st.markdown('<div class="tm-lg">' + ''.join(
        f'<span><i style="background:{WARNA_STATUS[k]}"></i>{KET_STATUS[k]} {hitung[k]}</span>' for k in WARNA_STATUS) + '</div>',
        unsafe_allow_html=True)


def heatmap(data):
    if not data:
        st.caption('Data harga belum tersedia.')
        return
    kode = list(data)
    nilai = [max(data[k]['harga'] * data[k]['volume'], 1) for k in kode]
    pct = [data[k]['ubah_pct'] for k in kode]
    fig = go.Figure(go.Treemap(
        labels=kode, parents=[''] * len(kode), values=nilai, text=[persen(p) for p in pct], textinfo='label+text',
        marker=dict(colors=pct, colorscale=[[0, '#E5484D'], [0.5, '#151A22'], [1, '#00AB6B']], cmin=-3, cmax=3,
                    line=dict(width=2, color='#0F1115'), pad=dict(t=0, l=0, r=0, b=0)),
        textfont=dict(family='ui-monospace,Menlo,monospace', size=14, color='white'),
        hovertemplate='<b>%{label}</b><br>%{text}<extra></extra>', tiling=dict(pad=1),
        pathbar=dict(visible=False), root_color='rgba(0,0,0,0)'))
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=335, paper_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig, width='stretch', config={'displayModeBar': False}, key='tm_heat')


def grafik_mini(data, kodes):
    bar = live.get_intraday(tuple(kodes))
    urut = sorted(data, key=lambda k: data[k]['harga'] * data[k]['volume'], reverse=True)[:4]
    for baris in (urut[:2], urut[2:4]):
        for kol, k in zip(st.columns(2), baris):
            x = data[k]
            d = bar.get(k)
            if d is None:
                continue
            d = d[d.index.date == x['tanggal']]
            kol.plotly_chart(grafik.mini(grafik.resample_ohlcv(d, 5), k, x['prev'], x['ubah_pct']), width='stretch',
                             config={'displayModeBar': False}, key='tm_mini_' + k)


def live_feed():
    log = st.session_state.get('jejak', [])
    if not log:
        isi = '<div class="info">Belum ada aktivitas. Jalankan Cek pasar, Kantor Agen, Riset Web, atau Sidang.</div>'
    else:
        isi = ''.join(f'<div><span class="t">[{x["t"]}]</span> <span class="s">{html.escape(x["s"]):<11}</span>'
                      f'<span class="{x["l"]}">{html.escape(x["x"])}</span></div>' for x in reversed(log[-40:]))
    st.markdown(f'<div class="tm-box tm-feed">{isi}</div>', unsafe_allow_html=True)


def jejak_putusan():
    h = st.session_state.get('kantor')
    if not h:
        st.markdown('<div class="tm-box tm-feed"><div class="info">Belum ada putusan. Jalankan Kantor Agen.</div></div>',
                    unsafe_allow_html=True)
        return
    urut = sorted(h['saham'].items(), key=lambda kv: (['BELI', 'TUNGGU', 'SKIP'].index(kv[1]['putusan']['putusan']),
                                                      -kv[1]['putusan']['keyakinan']))[:10]
    baris = []
    for k, x in urut:
        ks, p = x['kasir'], x['putusan']
        gaya = (x['lap'].get('ANALIS') or {}).get('gaya') or '-'
        baris.append(f'<tr><td><b>{k}</b></td><td><span class="tm-b {p["putusan"]}">{p["putusan"]}</span></td>'
                     f'<td>{p["keyakinan"]}/10</td><td>{html.escape(str(gaya))}</td><td>{ks["rr"] if ks else "-"}</td>'
                     f'<td>{ks["lot"] if ks else "-"}</td></tr>')
    st.markdown('<div class="tm-box"><table class="tm-tab"><tr><th>KODE</th><th>PUTUSAN</th><th>YAKIN</th><th>GAYA</th><th>RR</th>'
                '<th>LOT</th></tr>' + ''.join(baris) + '</table></div>', unsafe_allow_html=True)


def wallet():
    sim = st.session_state.get('sim') or sm.sim_baru(10_000_000)
    u, a = sm.ringkas_sisi(sim, 'u'), sm.ringkas_sisi(sim, 'a')
    stat = stat_jurnal(st.session_state.get('jurnal'))
    wr = f'{stat["total"]["win_rate_pct"]}%'.replace('.', ',') if stat else '-'
    kartu = [
        ('Ekuitas kamu', f'Rp{angka(u["ekuitas"])}', u['return_pct']),
        ('Ekuitas Tim AI', f'Rp{angka(a["ekuitas"])}', a['return_pct']),
        ('Win rate jurnal', wr, None),
        ('Posisi terbuka', f'{u["terbuka"]} · AI {a["terbuka"]}', None),
    ]
    st.markdown('<div class="tm-w">' + ''.join(
        f'<div><small>{t}</small><b>{v}</b>' + (f' <span class="{"up" if r >= 0 else "dn"}">{persen(r)}</span>' if r is not None else '')
        + '</div>' for t, v, r in kartu) + '</div>', unsafe_allow_html=True)


def halaman_terminal(kodes_default):
    st.markdown(CSS, unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1])
    otomatis = c1.toggle('Refresh otomatis', value=True, key='tm_oto')
    detik = c2.selectbox('Setiap', [15, 30, 60], index=1, format_func=lambda s: f'{s} detik', key='tm_detik',
                         label_visibility='collapsed')
    daftar = st.session_state.get('watchlist') or ','.join(kodes_default)
    kodes = tuple(dict.fromkeys(k.strip().upper() for k in daftar.split(',') if k.strip()))

    def isi():
        bar_status()
        data = live.harga_live(kodes)
        kiri, kanan = st.columns(2)
        with kiri:
            panel_judul('Neural shell · tim agen', f'{len(AGEN)} agen')
            bola_agen()
        with kanan:
            panel_judul('Heatmap watchlist', 'ukuran = nilai, warna = %')
            heatmap(data)
        panel_judul('Grafik live', '5 menit · 4 saham teratas menurut nilai transaksi')
        if data:
            grafik_mini(data, kodes)
        kiri, kanan = st.columns([1.15, 1])
        with kiri:
            panel_judul('Live feed', 'aktivitas terbaru di atas')
            live_feed()
        with kanan:
            panel_judul('Jejak putusan', 'hasil Kantor Agen terakhir')
            jejak_putusan()
        panel_judul('Wallet', 'simulasi modal virtual dan jurnal')
        wallet()

    st.fragment(run_every=detik if otomatis else None)(isi)()
