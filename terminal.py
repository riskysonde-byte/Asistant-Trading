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
import universe
from jejak import catat
from kantor import hitung_indikator, potong, ringkas_saham, skor_bull, stat_jurnal
from tema import angka, persen

WARNA_BOLA = {'BULLISH': '#00FF9C', 'NETRAL': '#F5B342', 'BEARISH': '#FF4D4F'}
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


BOLA = """
<canvas id="c" style="width:100%;height:340px;display:block;cursor:crosshair"></canvas>
<script>
const D = __DATA__;
const WARNA = __WARNA__;
const cv = document.getElementById('c'), ctx = cv.getContext('2d');
let W = 0, H = 0; const DPR = window.devicePixelRatio || 1;
function fit(){ W = cv.clientWidth; H = cv.clientHeight; cv.width = W*DPR; cv.height = H*DPR; ctx.setTransform(DPR,0,0,DPR,0,0); }
fit(); addEventListener('resize', () => { fit(); if (reduce) frame(0); });
const N = 800, P = [], GA = Math.PI*(3-Math.sqrt(5));
for (let i = 0; i < N; i++){ const y = 1-2*(i+.5)/N, r = Math.sqrt(1-y*y), th = GA*i; P.push([Math.cos(th)*r, y, Math.sin(th)*r, Math.random()*6.28]); }
// radius saham: skor +100 = pusat, 0 = tengah-tengah, -100 = tepi bola
const DS = D.slice().sort((a,b) => a.k < b.k ? -1 : 1);   // arah titik diacak dari skor agar tersebar merata
const ORD = D.slice().sort((a,b) => b.s-a.s);
const TAMPIL = new Set((D.length <= 40 ? D : ORD.slice(0,8).concat(ORD.slice(-8))).map(x => x.k));
const BASE = D.length > 300 ? 1.8 : D.length > 120 ? 2.6 : D.length > 40 ? 3.4 : 4.4;
const NODE = DS.map((d,i) => { const y = 1-2*(i+.5)/DS.length, r = Math.sqrt(1-y*y), th = GA*i*1.9;
  const rad = 0.09 + (1-(d.s+100)/200)*0.96; return {d, p:[Math.cos(th)*r*rad, y*rad, Math.sin(th)*r*rad]}; });
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
let ang = 0, hov = null, mx = -1, my = -1;
function rot(p, ay, ax){ const x = p[0]*Math.cos(ay)+p[2]*Math.sin(ay), z = -p[0]*Math.sin(ay)+p[2]*Math.cos(ay), y = p[1];
  return [x, y*Math.cos(ax)-z*Math.sin(ax), y*Math.sin(ax)+z*Math.cos(ax)]; }
function proj(q, R){ const s = 3.2/(3.2+q[2]*0.9); return [W/2+q[0]*R*s, H/2+q[1]*R*s, s]; }
function ring(rad, ay, ax, R){ ctx.beginPath(); for (let i = 0; i <= 72; i++){ const a = i/72*6.2832, s = proj(rot([Math.cos(a)*rad,0,Math.sin(a)*rad],ay,ax),R);
  i ? ctx.lineTo(s[0],s[1]) : ctx.moveTo(s[0],s[1]); } ctx.stroke(); }
function frame(t){
  ctx.clearRect(0,0,W,H); const R = Math.min(W,H)*0.38, ay = reduce ? 0.6 : ang, ax = 0.4;
  const g = ctx.createRadialGradient(W/2,H/2,0,W/2,H/2,R*1.3); g.addColorStop(0,'rgba(0,255,156,0.16)'); g.addColorStop(0.45,'rgba(0,255,156,0.04)'); g.addColorStop(1,'rgba(0,0,0,0)');
  ctx.fillStyle = g; ctx.fillRect(0,0,W,H);
  ctx.lineWidth = 0.6; ctx.strokeStyle = 'rgba(34,211,238,0.16)'; ring(0.36,ay,ax,R); ring(0.70,ay,ax,R); ring(1.0,ay,ax,R);
  for (const p of P){ const q = rot(p,ay,ax), s = proj(q,R), d = (q[2]+1)/2, tw = 0.6+0.4*Math.sin(t/700+p[3]);
    ctx.fillStyle = 'rgba(120,255,214,'+(0.08+0.4*d*tw).toFixed(3)+')'; const z = 1.1*s[2]+0.3; ctx.fillRect(s[0],s[1],z,z); }
  const c0 = proj([0,0,0],R), pc = 1+0.25*Math.sin(t/400);
  ctx.shadowColor = '#00FF9C'; ctx.shadowBlur = 22; ctx.fillStyle = 'rgba(0,255,156,0.9)'; ctx.beginPath(); ctx.arc(c0[0],c0[1],5*pc,0,6.283); ctx.fill(); ctx.shadowBlur = 0;
  const pts = NODE.map(n => ({n, q: rot(n.p,ay,ax)})).map(o => ({...o, s: proj(o.q,R)}));
  ctx.lineWidth = 0.7;
  for (const o of pts){ const col = WARNA[o.n.d.l]; ctx.strokeStyle = col; ctx.globalAlpha = 0.08+0.1*(o.q[2]+1)/2;
    ctx.beginPath(); ctx.moveTo(c0[0],c0[1]); ctx.lineTo(o.s[0],o.s[1]); ctx.stroke(); }
  ctx.globalAlpha = 1;
  pts.sort((a,b) => a.q[2]-b.q[2]);
  hov = null; let best = D.length > 120 ? 10 : 16;
  for (const o of pts){ const dd = Math.hypot(o.s[0]-mx, o.s[1]-my); if (dd < best){ best = dd; hov = o; } }
  const taken = [];
  for (const o of pts){
    const d = o.n.d, col = WARNA[d.l], front = o.q[2] > -0.2, strong = (d.s >= 60 && D.length <= 120) ? 1+0.3*Math.sin(t/260+o.n.p[1]*5) : 1;
    const size = (hov === o ? 6.5 : BASE)*o.s[2]*strong;
    ctx.globalAlpha = front ? 1 : 0.4; ctx.shadowColor = col; ctx.shadowBlur = D.length > 300 ? 0 : (d.l === 'BULLISH' ? 14 : 7); ctx.fillStyle = col;
    ctx.beginPath(); ctx.arc(o.s[0],o.s[1],size,0,6.283); ctx.fill(); ctx.shadowBlur = 0;
    if ((front && TAMPIL.has(d.k)) || hov === o){
      const lx = o.s[0]+(o.s[0] > W/2 ? 9 : -9), ly = o.s[1]+3;
      if (hov === o || !taken.some(t => Math.abs(t[0]-lx) < 50 && Math.abs(t[1]-ly) < 11)){
        taken.push([lx, ly]); ctx.font = '600 10px ui-monospace,Menlo,monospace'; ctx.textAlign = o.s[0] > W/2 ? 'left' : 'right';
        ctx.fillText(d.k+' '+(d.s>0?'+':'')+d.s, lx, ly); } }
    ctx.globalAlpha = 1; }
  if (hov){ const d = hov.n.d, x = 8, y = H-62;
    const l1 = d.k+'  '+d.l+'  skor '+(d.s>0?'+':'')+d.s, l2 = 'Rp'+d.h+'  '+(d.u>0?'+':'')+d.u+'%'+(d.n != null ? '  ·  Rp'+d.n+' M/hari' : ''), l3 = d.a;
    ctx.font = '700 11px ui-monospace,Menlo,monospace'; let w = ctx.measureText(l1).width;
    ctx.font = '10px ui-monospace,Menlo,monospace'; w = Math.min(W-16, Math.max(w, ctx.measureText(l2).width, ctx.measureText(l3).width)+16);
    ctx.fillStyle = 'rgba(8,20,24,0.92)'; ctx.fillRect(x,y,w,54); ctx.strokeStyle = WARNA[d.l]; ctx.lineWidth = 1; ctx.strokeRect(x,y,w,54);
    ctx.textAlign = 'left'; ctx.font = '700 11px ui-monospace,Menlo,monospace'; ctx.fillStyle = WARNA[d.l]; ctx.fillText(l1, x+8, y+16);
    ctx.font = '10px ui-monospace,Menlo,monospace'; ctx.fillStyle = '#C9D1D9'; ctx.fillText(l2, x+8, y+30);
    ctx.fillStyle = '#8B93A1'; ctx.fillText(l3, x+8, y+44); }
  if (!reduce){ ang += 0.003; requestAnimationFrame(frame); }
}
function pos(e){ const r = cv.getBoundingClientRect(), t = e.touches ? e.touches[0] : e; mx = t.clientX-r.left; my = t.clientY-r.top; if (reduce) frame(0); }
cv.addEventListener('mousemove', pos); cv.addEventListener('touchstart', pos, {passive:true});
cv.addEventListener('mouseleave', () => { mx = my = -1; if (reduce) frame(0); });
requestAnimationFrame(frame);
</script>
"""


def _skor_satu(k, df, lv=None):
    """Skor satu saham dari data harian (opsional digabung harga live). None jika data kurang."""
    d = hitung_indikator(live.sambung_live(df, lv) if lv else df)
    if len(d) < 60 or d['MA50'].isna().iloc[-1]:
        return None
    tk = ringkas_saham(k, d)
    sk = skor_bull(tk)
    if not sk:
        return None
    nv = float((d['Close'] * d['Volume']).tail(20).mean()) / 1e9     # nilai transaksi rata-rata/hari, miliar Rp
    return {'k': k, 's': sk['skor'], 'l': sk['label'], 'h': angka(tk['harga']), 'u': round(tk['ubah_pct'], 2),
            'n': round(nv, 1), 'a': ' · '.join(sk['alasan'][:3])}


def skor_watchlist(data, kodes):
    """Skor bullish/bearish watchlist dari data harian + harga terkini. Terurut dari paling bullish."""
    try:
        harian = live.get_harian_banyak(tuple(kodes), '1y')
    except Exception:
        return []
    hasil = []
    for k in kodes:
        try:
            x = _skor_satu(k, harian[k], data.get(k))
        except Exception:
            continue
        if x:
            hasil.append(x)
    return sorted(hasil, key=lambda x: -x['s'])


def muat_universe(jumlah):
    """Ambil data harian emiten terbesar (jumlah = 0 berarti semua), per 100 kode, lalu hitung skornya. Disimpan di sesi."""
    kodes, sumber = universe.daftar()
    kodes = kodes[:jumlah] if jumlah else kodes
    kelompok = potong(kodes, 100)
    bar = st.progress(0.0, text=f'Mengambil data {len(kodes)} saham ({sumber})...')
    hasil = []
    for i, grup in enumerate(kelompok):
        try:
            harian = live.get_harian_banyak(tuple(grup), '6mo')
        except Exception:
            harian = {}
        for k, df in harian.items():
            try:
                x = _skor_satu(k, df)
            except Exception:
                continue
            if x:
                hasil.append(x)
        bar.progress((i + 1) / len(kelompok), text=f'{min((i + 1) * 100, len(kodes))}/{len(kodes)} saham diproses · {len(hasil)} berhasil')
    bar.empty()
    st.session_state['univ'] = {'t': live.sekarang(), 'skor': sorted(hasil, key=lambda x: -x['s']),
                                'diminta': len(kodes), 'sumber': sumber}
    catat('TERMINAL', f'Bola seluruh pasar: {len(hasil)} dari {len(kodes)} saham ({sumber})', 'ok' if hasil else 'warn')


def bola_saham(skor):
    if not skor:
        st.caption('Skor belum bisa dihitung (data harian Yahoo belum tersedia).')
        return
    components.html(BOLA.replace('__DATA__', json.dumps(skor)).replace('__WARNA__', json.dumps(WARNA_BOLA)), height=345)
    n = {k: sum(1 for x in skor if x['l'] == k) for k in WARNA_BOLA}
    st.markdown('<div class="tm-lg">' + ''.join(f'<span><i style="background:{w}"></i>{k} {n[k]}</span>' for k, w in WARNA_BOLA.items())
                + '<span>tengah = paling bullish · makin ke tepi = makin bearish</span></div>', unsafe_allow_html=True)
    atas = ', '.join(f'<b class="up">{x["k"]} {x["s"]:+d}</b>' for x in skor[:3])
    bawah = ', '.join(f'<b class="dn">{x["k"]} {x["s"]:+d}</b>' for x in reversed(skor[-3:]) if x['s'] < 0)
    st.markdown(f'<div class="tm-lg" style="margin-top:.3rem"><span>TERKUAT: {atas}</span>'
                + (f'<span>TERLEMAH: {bawah}</span>' if bawah else '') + '</div>', unsafe_allow_html=True)


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
    cakupan = st.segmented_control('Cakupan bola', ['Watchlist', 'Seluruh IDX'], default='Watchlist', key='tm_cakupan') or 'Watchlist'
    likuid = 1
    if cakupan == 'Seluruh IDX':
        k1, k2, k3 = st.columns([1, 1, 1])
        jumlah = k2.select_slider('Jumlah saham dimuat (terbesar dulu)', options=[50, 100, 200, 400, 0], value=100,
                                  format_func=lambda v: 'semua' if v == 0 else str(v), key='tm_jumlah')
        likuid = k3.select_slider('Likuiditas minimal (per hari)', options=[0, 0.5, 1, 2, 5, 10, 25], value=1,
                                  format_func=lambda v: 'semua' if v == 0 else f'≥ Rp{v} M', key='tm_likuid')
        if k1.button('Muat / perbarui data', key='tm_muat', type='primary'):
            muat_universe(jumlah)
    daftar = st.session_state.get('watchlist') or ','.join(kodes_default)
    kodes = tuple(dict.fromkeys(k.strip().upper() for k in daftar.split(',') if k.strip()))

    def isi():
        bar_status()
        data = live.harga_live(kodes)
        kiri, kanan = st.columns(2)
        with kiri:
            if cakupan == 'Seluruh IDX':
                u = st.session_state.get('univ')
                skor = [x for x in u['skor'] if x['n'] >= likuid] if u else []
                panel_judul('Bull sphere · pasar IDX', f'{len(skor)} saham' if u else 'belum dimuat')
                if u:
                    st.caption(f'Data harian {u["t"]:%d-%m %H:%M} · {len(u["skor"])} dari {u["diminta"]} saham terbaca ({u["sumber"]}) · '
                               f'{len(skor)} lolos filter likuiditas')
                else:
                    st.info('Tekan "Muat / perbarui data" di atas. Memuat 100 saham biasanya hanya sebentar.')
                bola_saham(skor)
            else:
                panel_judul('Bull sphere · peta kekuatan saham', 'tengah = bullish')
                bola_saham(skor_watchlist(data, kodes))
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
