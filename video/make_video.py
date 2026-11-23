import numpy as np, subprocess, wave, math, random, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

SRC = sys.argv[1]
OUT = sys.argv[2]
W, H, FPS, DUR = 1080, 1920, 30, 26
N = FPS * DUR
rng = np.random.default_rng(7)
random.seed(7)

FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FS = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
FM = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
def font(p, s): return ImageFont.truetype(p, s)

# ---------- base image: crop away screenshot frame, cover 1080x1920 ----------
im = Image.open(SRC).convert("RGB")
im = im.crop((8, 102, im.width - 8, 1922))
sc = max(W / im.width, H / im.height) * 1.0
im = im.resize((round(im.width * sc), round(im.height * sc)), Image.LANCZOS)
BIG = im.resize((im.width * 2 // 1, im.height * 2 // 1), Image.LANCZOS)  # for zooms
BW, BH = BIG.size

def view(cx, cy, zoom):
    """cx,cy in 0..1 of image, zoom>=1"""
    w = BW / zoom * (W / (BW / 2)) / 2 * 1.0
    w = W * 2 / zoom
    h = H * 2 / zoom
    x0 = min(max(cx * BW - w / 2, 0), BW - w)
    y0 = min(max(cy * BH - h / 2, 0), BH - h)
    return np.asarray(BIG.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + w, y0 + h)), dtype=np.float32)

# vignette
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
VIG = np.clip(1.15 - 0.75 * d ** 1.6, 0.05, 1)[..., None]
SCAN = (1 - 0.10 * ((np.arange(H) % 4) < 2)).astype(np.float32)[:, None, None]

def grade(a, red=0.0, dark=0.0):
    lum = a.mean(axis=2, keepdims=True)
    a = a * 0.55 + lum * 0.45                    # desaturate
    a = a * np.array([0.92, 0.97, 1.08])         # cold teal
    if red > 0:
        a = a * (1 - red) + (lum * np.array([1.6, 0.25, 0.25])) * red
    a = (a - 128) * 1.18 + 118                   # contrast
    a = a * VIG * (1 - dark)
    return a

def grain(a, amt=9):
    g = rng.normal(0, amt, (H // 2, W // 2, 1)).astype(np.float32)
    g = np.repeat(np.repeat(g, 2, 0), 2, 1)
    return a + g

def glitch(a, strength):
    if strength <= 0: return a
    out = a.copy()
    s = int(18 * strength) + 2
    out[..., 0] = np.roll(a[..., 0], s, axis=1)
    out[..., 2] = np.roll(a[..., 2], -s, axis=1)
    for _ in range(int(10 * strength)):
        y = random.randint(0, H - 80); h = random.randint(8, 90)
        out[y:y + h] = np.roll(out[y:y + h], random.randint(-160, 160), axis=1)
    return out

# ---------- candle chart overlay ----------
def chart_layer(t, crash=False, alpha=1.0):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    rs = random.Random(3 if not crash else 9)
    price = 1100.0
    n = 40
    shown = int(min(1, t) * n)
    for i in range(shown):
        o = price
        drift = -38 if (crash and i > n * 0.45) else rs.uniform(-25, 25)
        c = o + drift + rs.uniform(-30, 30)
        hi = max(o, c) + rs.uniform(5, 40); lo = min(o, c) - rs.uniform(5, 40)
        x = 60 + i * 24
        col = (220, 30, 40, int(200 * alpha)) if c > o else (230, 230, 230, int(120 * alpha))
        if crash: col = (230, 20, 30, int(220 * alpha)) if c < o else (120, 120, 120, int(110 * alpha))
        dr.line([(x + 7, H - hi * 0.7 - 200), (x + 7, H - lo * 0.7 - 200)], fill=col, width=2)
        y1, y2 = sorted([H - o * 0.7 - 200, H - c * 0.7 - 200])
        dr.rectangle([x, y1, x + 14, max(y2, y1 + 2)], fill=col)
        price = c
    return layer

def overlay(a, layer):
    l = np.asarray(layer, dtype=np.float32)
    al = l[..., 3:4] / 255
    return a * (1 - al) + l[..., :3] * al

# ---------- text ----------
def text_layer(lines, t, size=64, fnt=FB, y=None, color=(235, 235, 235), typewriter=False,
               glow=(200, 0, 20), spacing=1.25):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    f = font(fnt, size)
    total = sum(len(l) for l in lines)
    show = int(total * min(1, t * 1.6)) if typewriter else total
    lh = int(size * spacing)
    y0 = y if y is not None else H // 2 - lh * len(lines) // 2
    cnt = 0
    for i, l in enumerate(lines):
        part = l[:max(0, min(len(l), show - cnt))]
        cnt += len(l)
        tw = dr.textlength(l, font=f)
        dr.text(((W - tw) / 2, y0 + i * lh), part, font=f, fill=color + (255,))
    if glow:
        g = layer.copy().filter(ImageFilter.GaussianBlur(14))
        gl = Image.new("RGBA", (W, H), glow + (0,))
        gl.putalpha(g.split()[3].point(lambda v: min(255, v * 2)))
        base = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        base.alpha_composite(gl); base.alpha_composite(layer)
        layer = base
    return layer

def fade(t, a, b, fi=0.4, fo=0.4):
    if t < a or t > b: return 0.0
    return min(1, (t - a) / fi, (b - t) / fo)

def blend_text(a, layer, alpha):
    if alpha <= 0: return a
    l = np.asarray(layer, dtype=np.float32)
    al = l[..., 3:4] / 255 * alpha
    return a * (1 - al) + l[..., :3] * al

# ---------- scenes ----------
SCENES = [
    # (start, end, lines, size, font, y, typewriter)
    (0.6, 3.4,  ["> SINYAL TIDAK DIKENAL", "> TERDETEKSI..."], 54, FM, 820, True),
    (4.2, 7.4,  ["Tidak ada yang tahu", "siapa dia."], 72, FS, 1450, False),
    (7.8, 11.0, ["Dia tidak pernah", "menunjukkan wajahnya."], 66, FS, 1450, False),
    (11.4, 14.8, ["Saat market panik...", "dia sudah menunggu."], 66, FS, 1450, False),
    (15.2, 18.6, ["Semua orang melihat grafik.", "Dia melihat POLA."], 58, FS, 1450, False),
]

pipe = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
                         "-crf", "25", "-pix_fmt", "yuv420p", OUT + ".noaudio.mp4"], stdin=subprocess.PIPE)

glitch_times = [3.6, 7.6, 11.2, 15.0, 19.0, 19.15]
def near(t, ts, w=0.18):
    return max([max(0, 1 - abs(t - x) / w) for x in ts] + [0])

text_cache = {}
for fi in range(N):
    t = fi / FPS
    if t < 3.6:
        a = np.zeros((H, W, 3), np.float32) + 4
        a = overlay(a, chart_layer((t - 0.2) / 3.0, crash=False, alpha=0.55))
        a = a * VIG
    elif t < 19.0:
        # camera moves per segment
        if t < 7.6:   p = (t - 3.6) / 4.0; img = view(0.5, 0.52, 1.0 + 0.12 * p); red = 0; dark = 0.35 * (1 - p)
        elif t < 11.2: p = (t - 7.6) / 3.6; img = view(0.17, 0.33, 1.9 + 0.35 * p); red = 0.15; dark = 0
        elif t < 15.0: p = (t - 11.2) / 3.8; img = view(0.5, 0.44, 1.5 + 0.25 * p); red = 0.55; dark = 0
        else:         p = (t - 15.0) / 4.0; img = view(0.5, 0.9, 1.6 - 0.25 * p); red = 0.25; dark = 0
        a = grade(img, red=red, dark=dark)
        if 11.2 <= t < 15.0:
            a = overlay(a, chart_layer((t - 11.2) / 2.5, crash=True, alpha=0.6))
        # flicker
        if random.random() < 0.06: a *= 0.55
    else:
        # title card
        p = (t - 19.0)
        img = view(0.5, 0.45, 1.05 + 0.02 * p)
        a = grade(img, red=0.35, dark=0.6)
        a = a * 0.6

    a = glitch(a, near(t, glitch_times) + (0.25 if random.random() < 0.02 and t > 3.6 else 0))

    for (s, e, lines, sz, fn, y, tw) in SCENES:
        al = fade(t, s, e)
        if al > 0:
            if tw:
                lay = text_layer(lines, (t - s) / (e - s), sz, fn, y, (210, 40, 50), True, glow=(160, 0, 10))
            else:
                key = (s,)
                if key not in text_cache: text_cache[key] = text_layer(lines, 1, sz, fn, y)
                lay = text_cache[key]
            jit = near(t, [s + 0.05], 0.15)
            a = blend_text(a, lay, al)
            if jit: a = glitch(a, jit * 0.6)

    if t >= 19.3:
        al1 = fade(t, 19.3, 30, 0.25, 1)
        if "title" not in text_cache:
            text_cache["title"] = text_layer(["THE MASKED", "TRADER"], 1, 118, FS, 580, (240, 240, 240), glow=(210, 0, 20), spacing=1.1)
            text_cache["sub"] = text_layer(["Diam. Sabar. Mematikan."], 1, 52, FS, 900, (200, 30, 40), glow=None)
            text_cache["cta"] = text_layer(["Mau tahu cara dia membaca market?", "GABUNG SEKARANG"], 1, 50, FB, 1300, (235, 235, 235), glow=(200, 0, 20), spacing=1.6)
            text_cache["disc"] = text_layer(["Trading berisiko tinggi. Bukan ajakan investasi."], 1, 28, FB, 1820, (150, 150, 150), glow=None)
        a = blend_text(a, text_cache["title"], al1)
        if t > 19.15: a = glitch(a, near(t, [19.35], 0.2) * 0.9)
        a = blend_text(a, text_cache["sub"], fade(t, 20.6, 30, 0.6, 1))
        cta = fade(t, 21.8, 30, 0.5, 1) * (0.75 + 0.25 * math.sin(t * 6))
        a = blend_text(a, text_cache["cta"], cta)
        a = blend_text(a, text_cache["disc"], fade(t, 22.0, 30, 0.5, 1))

    a = a * SCAN
    a = grain(a)
    # global fade in/out
    a *= min(1, t / 0.5, (DUR - t) / 0.8)
    pipe.stdin.write(np.clip(a, 0, 255).astype(np.uint8).tobytes())
    if fi % 60 == 0: print(f"frame {fi}/{N}", flush=True)
pipe.stdin.close(); pipe.wait()

# ---------- audio ----------
SR = 44100
ns = SR * DUR
tt = np.arange(ns) / SR
aud = np.zeros(ns)
# dark drone with beating
drone = (np.sin(2 * np.pi * 41 * tt) + 0.7 * np.sin(2 * np.pi * 41.7 * tt) + 0.35 * np.sin(2 * np.pi * 61.5 * tt)
         + 0.15 * np.sin(2 * np.pi * 123.3 * tt + np.sin(2 * np.pi * 0.2 * tt)))
aud += 0.22 * drone * np.clip(tt / 3, 0, 1)
# eerie high tone (dissonant)
aud += 0.025 * (np.sin(2 * np.pi * 880 * tt) + np.sin(2 * np.pi * 932 * tt)) * np.clip((tt - 4) / 6, 0, 1) * (tt < 19)
# heartbeat
def thump(t0, amp):
    i0 = int(t0 * SR); L = int(0.25 * SR)
    if i0 + L > ns: return
    e = np.exp(-np.arange(L) / (0.045 * SR))
    f = 55 * np.exp(-np.arange(L) / (0.08 * SR)) + 35
    aud[i0:i0 + L] += amp * e * np.sin(2 * np.pi * np.cumsum(f) / SR)
bt = 3.6
while bt < 19:
    rate = 1.1 - 0.45 * (bt - 3.6) / 15.4
    thump(bt, 0.9); thump(bt + 0.22, 0.6); bt += rate
# glitch noise bursts
nz = np.random.default_rng(1).normal(0, 1, ns)
for g in glitch_times + [s for (s, *_r) in SCENES]:
    i0 = int(g * SR); L = int(0.16 * SR)
    seg = nz[i0:i0 + L] * (np.sign(np.sin(2 * np.pi * 70 * np.arange(L) / SR)))
    aud[i0:i0 + L] += 0.35 * seg[:len(aud[i0:i0 + L])] * np.linspace(1, 0, L)[:len(aud[i0:i0 + L])]
# typewriter ticks in intro
for k in range(28):
    tk = 0.7 + k * 0.085
    i0 = int(tk * SR); L = int(0.012 * SR)
    aud[i0:i0 + L] += 0.25 * nz[i0:i0 + L]
# rising riser before title
m = (tt > 15.5) & (tt < 19.0)
rp = (tt[m] - 15.5) / 3.5
aud[m] += 0.18 * rp ** 2 * np.sin(2 * np.pi * np.cumsum(200 + 900 * rp ** 2) / SR) + 0.12 * rp ** 3 * nz[m]
# BOOM on title
i0 = int(19.3 * SR); L = int(3.5 * SR)
e = np.exp(-np.arange(L) / (0.7 * SR))
f = 70 * np.exp(-np.arange(L) / (0.3 * SR)) + 28
aud[i0:i0 + L] += 1.2 * e * np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.3 * e * nz[i0:i0 + L] * np.exp(-np.arange(L) / (0.08 * SR))
# drop the drone into silence just before boom
aud *= np.where((tt > 18.85) & (tt < 19.3), 0.15, 1)
# simple echo
dl = int(0.33 * SR); wet = np.zeros(ns); wet[dl:] = aud[:-dl] * 0.35
aud = aud + wet
aud *= np.clip((DUR - tt) / 1.0, 0, 1)
aud = np.tanh(aud * 1.1) / np.tanh(1.1) * 0.9
pcm = (aud * 32767).astype(np.int16)
with wave.open(OUT + ".wav", "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())

subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", OUT + ".noaudio.mp4", "-i", OUT + ".wav",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-shortest", "-movflags", "+faststart", OUT], check=True)
print("done")
