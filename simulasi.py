"""Simulasi modal virtual: kamu lawan Tim AI. Logika murni tanpa Streamlit."""

PORSI = 0.25          # maks 25% modal awal per posisi
MAKS_POSISI_AI = 4
RR_MIN_AI = 1.5


def sim_baru(modal):
    return {'modal': modal, 'u': {'kas': modal, 'pos': [], 'rw': []},
            'a': {'kas': modal, 'pos': [], 'rw': []}, 'log': []}


def ekuitas(s):
    return s['kas'] + sum(p['lot'] * 100 * (p.get('last') or p['beli']) for p in s['pos'])


def sim_buka(sim, sisi, p, waktu='', porsi=PORSI):
    """p: {kode, gaya, beli, tp, sl, lot}. Hasil: (berhasil, pesan)."""
    s = sim[sisi]
    if any(x['kode'] == p['kode'] for x in s['pos']):
        return False, 'Sudah ada di simulasi'
    maks = min(s['kas'], sim['modal'] * porsi, max(p['lot'], 1) * 100 * p['beli'])
    lot = int(maks // (p['beli'] * 100))
    if lot < 1:
        return False, 'Kas simulasi kurang'
    s['kas'] -= lot * 100 * p['beli']
    s['pos'].append({'kode': p['kode'], 'gaya': p.get('gaya') or '-', 'beli': p['beli'], 'tp': p['tp'],
                     'sl': p['sl'], 'lot': lot, 't': waktu, 'last': p['beli']})
    return True, 'Diikuti'


def sim_tutup(sim, sisi, i, harga, status, waktu=''):
    s = sim[sisi]
    if not 0 <= i < len(s['pos']):
        return None
    p = s['pos'][i]
    pl = (harga - p['beli']) * p['lot'] * 100
    s['kas'] += harga * p['lot'] * 100
    s['rw'].insert(0, {'kode': p['kode'], 'gaya': p['gaya'], 'beli': p['beli'], 'jual': harga, 'lot': p['lot'],
                       'pl': pl, 'status': status, 't': waktu})
    del s['rw'][60:]
    del s['pos'][i]
    return {'kode': p['kode'], 'status': status, 'pl': pl, 'sisi': sisi}


def sim_harga(sim, sisi, kode, harga, waktu=''):
    """Perbarui harga terakhir. Kena TP dijual di TP; kena SL dijual di harga saat itu (bisa gap)."""
    s, kejadian = sim[sisi], []
    for i in range(len(s['pos']) - 1, -1, -1):
        p = s['pos'][i]
        if p['kode'] != kode:
            continue
        p['last'] = harga
        if harga >= p['tp']:
            kejadian.append(sim_tutup(sim, sisi, i, p['tp'], 'Kena TP', waktu))
        elif harga <= p['sl']:
            kejadian.append(sim_tutup(sim, sisi, i, harga, 'Kena SL', waktu))
    return kejadian


def sim_sinkron(sim, harga_map, rencana, waktu=''):
    """Perbarui semua posisi dengan harga terbaru, lalu Tim AI membuka posisi dari rencana BELI.
    rencana: [{kode, gaya, beli, tp, sl, lot, rr}]. Hasil: daftar teks log."""
    kejadian = []
    for sisi in ('u', 'a'):
        for p in list(sim[sisi]['pos']):
            h = harga_map.get(p['kode'])
            if h and h > 0:
                kejadian += sim_harga(sim, sisi, p['kode'], h, waktu)
    baru = 0
    for p in rencana:
        if p['lot'] >= 1 and p['rr'] >= RR_MIN_AI and len(sim['a']['pos']) < MAKS_POSISI_AI:
            if sim_buka(sim, 'a', p, waktu)[0]:
                baru += 1
    log = [('Kamu: ' if e['sisi'] == 'u' else 'Tim AI: ') + f'{e["kode"]} {e["status"]} {e["pl"]:+,.0f}'.replace(',', '.')
           for e in kejadian if e]
    if baru:
        log.append(f'Tim AI membuka {baru} posisi baru')
    sim['log'] = log
    return log


def ringkas_sisi(sim, sisi):
    s = sim[sisi]
    menang = sum(1 for x in s['rw'] if x['pl'] >= 0)
    e = ekuitas(s)
    return {'ekuitas': e, 'return_pct': (e / sim['modal'] - 1) * 100, 'menang': menang,
            'kalah': len(s['rw']) - menang, 'terbuka': len(s['pos'])}
