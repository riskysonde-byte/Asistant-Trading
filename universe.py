"""Daftar emiten IDX untuk bola 'seluruh pasar'.

Urutan sumber: (1) screener Yahoo saat aplikasi berjalan, (2) daftar saham likuid bawaan di bawah.
Kode yang sudah tidak ada (delisting) tidak masalah: datanya kosong dan otomatis dilewati.
"""
import re

import streamlit as st
import yfinance as yf

# Saham terbesar dan paling likuid lebih dulu (kira-kira LQ45 + IDX80), supaya "N saham pertama" masuk akal.
PRIORITAS = """
BBCA BBRI BMRI BBNI TLKM ASII AMMN BREN BYAN DCII TPIA CUAN GOTO ADRO UNVR ICBP INDF KLBF MDKA ANTM PTBA ITMG BRPT CPIN SMGR
INTP UNTR AKRA PGAS MEDC BRIS ARTO EXCL ISAT TOWR MTEL BSDE CTRA PWON SMRA JSMR MAPI AMRT ACES ERAA MIKA HEAL SIDO TBIG INKP
TKIM MBMA NCKL HRUM INDY ADMR ESSA BUMI SCMA EMTK BUKA MYOR GGRM HMSP JPFA MAIN SMAR AALI LSIP TINS INCO BBTN BNGA BDMN PNBN
MEGA NISP BTPS BJBR BJTM GJTL AUTO PGEO RAJA ENRG ELSA SSIA WIKA PTPP ADHI MLPT MTDL CMRY ULTJ ROTI HOKI BBHI BBYB AGRO INET
DSNG SSMS TBLA SIMP KAEF IRRA MPMX LPKR ASRI JRPT TOWR BRMS HEXA DOID PSAB MYOH TOBA SRTG TOTO WIFI
""".split()

# Cadangan lain: saham likuid tambahan.
BAWAAN = """
BBCA BBRI BMRI BBNI BRIS BBTN BNGA BDMN BNII PNBN MEGA BJBR BJTM NISP BTPN BTPS MAYA BNLI BBYB ARTO BABP BACA BCIC BGTG BINA
BMAS BNBA BSIM BVIC MCOR NOBU SDRA AGRO AMAR MASB PNBS BBHI BBMD BBSI BEKS
TLKM EXCL ISAT FREN TOWR TBIG MTEL SUPR LINK CENT GOTO BUKA EMTK DCII MLPT MTDL EDGE IRSX WIFI TOSK INET BELI
ADRO ADMR ITMG PTBA BUMI BYAN HRUM INDY KKGI GEMS MBMA MDKA ANTM INCO TINS NCKL PSAB AMMN MEDC PGAS ELSA AKRA ENRG ESSA RAJA RATU
PGEO BIPI DEWA DOID MYOH TOBA ABMM APEX BSSR DSSA PTRO SMMT UNTR HEXA MBAP CUAN BRMS BREN BRPT TPIA ARII HILL RMKE FIRE
ICBP INDF UNVR MYOR GGRM HMSP WIIM KLBF SIDO CPIN JPFA MAIN SMAR AALI LSIP TBLA SIMP DSNG SSMS BISI ULTJ CLEO CMRY ROTI GOOD CAMP
HOKI KINO TCID MBTO PYFA ERAA MAPI ACES AMRT MIDI LPPF RALS MAPA ASII AUTO IMAS SMSM GJTL BRAM DLTA STTP TGKA GZCO PALM ANJT
BSDE CTRA PWON SMRA LPKR ASRI DMAS KIJA JRPT MKPI BKSL DILD APLN PPRO WIKA PTPP ADHI JSMR META TOTL NRCA ACST SSIA TOTO WTON
SMGR INTP SMCB SMBR WSBP MTLA PLIN CSIS BEST GMTD DUTI MDLN LCGP ELTY
MIKA HEAL SILO PRDA SAME KAEF IRRA SRAJ DVLA TSPC PEHA BMHS MTMH
SRTG MPMX ASGR ISSP KRAS TKIM INKP ARNA AMFG FASW SPMA SCMA MNCN BMTR MSIN IPTV FILM VIVA
BIRD SMDR TMAS ASSA GIAA BLTA HITS NELY PSSI TRUK SAFE
PNLF AMAG ASJT LPGI PNIN MREI TUGU
INDS BRNA SMSM UNIC IPOL ALDO AKPI TRST CPRO JAWA MGRO NIKL DGWG
BNBR ESIP IFII INPP LPCK MYRX BIKA RODA FMII
JIHD KBLM MLBI MLIA PBSA PTSN PZZA RICY SCPI SGRO SKBM SKLT SOHO TALF TFCO UCID VOKS WOOD
POWR KEEN NRCA ZINC OKAS DKFT TRIN TURI SMRU SQMI GWSA FPNI HDFA
AGII ARTA BAPA BAYU BBLD BCAP BIPP BKDP BOLT BPII BRMS BTEK BUDI CASS CEKA COCO CSAP CTBN DART DEFI DPNS DYAN
EKAD ENZO EPMT FAST GDST GDYR GGRP GOLL GPRA HERO HKMU IBST ICON INAF INAI INCI INDR INTD JECC JKON JSKY KDSI KICI KIOS
KMTR KOIN LAPD LMPI LTLS MAGP MAPB MARI MBSS MDIA MERK MFMI MIRA MITI MKNT MOLI MPPA MRAT MSKY MTFN MTSM NASA NFCX
OMRE PADI PANR PBID PCAR PGLI PICO PJAA PLAS PNGO PORT PRAS PSDN PTBA PTIS PURE RDTX REAL RELI RIGS RIMO ROCK SAMF SDPC
SHID SIPD SKRN SMDM SMKL SONA SPTO SSTM TAMU TARA TAXI TBMS TCPI TGRA TIRA TLDN TMPO TOTL TRAM TRIS UANG UNSP VICO VINS WAPO WICO WINS YPAS ZBRA
""".split()


def _bersih(kode):
    k = re.sub(r'[^A-Z]', '', str(kode).upper())
    return k if len(k) == 4 else None


def bawaan():
    hasil = []
    for k in PRIORITAS + BAWAAN:
        k = _bersih(k)
        if k and k not in hasil:
            hasil.append(k)
    return hasil


def dari_screener(maks=1500):
    """Semua saham bursa Jakarta dari screener Yahoo (halaman 250 per permintaan). Gagal = daftar kosong."""
    try:
        q = yf.EquityQuery('eq', ['exchange', 'JKT'])
        hasil, offset = [], 0
        while offset < maks:
            r = yf.screen(q, offset=offset, size=250, sortField='intradaymarketcap', sortAsc=False)
            quotes = (r or {}).get('quotes') or []
            if not quotes:
                break
            for x in quotes:
                sim = str(x.get('symbol', ''))
                k = _bersih(sim[:-3]) if sim.endswith('.JK') else None
                if k and k not in hasil:
                    hasil.append(k)
            offset += 250
            if offset >= int((r or {}).get('total') or 0):
                break
        return hasil
    except Exception:
        return []


@st.cache_data(ttl=86400, show_spinner=False)
def daftar():
    """(daftar kode, sumber). Screener dipakai jika hasilnya masuk akal (lebih dari 300 saham)."""
    s = dari_screener()
    if len(s) > 300:
        return s, 'Yahoo screener'
    return bawaan(), 'daftar bawaan'
