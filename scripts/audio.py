"""Synthesises music + sound effects and mixes them under the narration -> audio/mix.wav"""
import numpy as np, soundfile as sf, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import timeline as T

SR = 48000
rng = np.random.default_rng(3)


def load_vo(sid):
    x, sr = sf.read(os.path.join(T.ROOT, "audio", f"{sid}.wav"))
    if x.ndim > 1:
        x = x.mean(axis=1)
    # resample 24k -> 48k
    t_old = np.arange(len(x)) / sr
    t_new = np.arange(int(len(x) * SR / sr)) / SR
    return np.interp(t_new, t_old, x)


def env(n, a=0.002, d=0.2):
    t = np.arange(n) / SR
    e = np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / d)
    return e


def lp_fast(x, cutoff):
    from scipy.signal import butter, sosfilt
    return sosfilt(butter(2, cutoff, 'low', fs=SR, output='sos'), x)


def hp_fast(x, cutoff):
    from scipy.signal import butter, sosfilt
    return sosfilt(butter(2, cutoff, 'high', fs=SR, output='sos'), x)


def bp_fast(x, lo, hi):
    from scipy.signal import butter, sosfilt
    return sosfilt(butter(2, [lo, hi], 'band', fs=SR, output='sos'), x)


def reverb(x, decay=1.2, mix=0.3):
    n = int(SR * decay)
    ir = rng.standard_normal(n) * np.exp(-np.arange(n) / (SR * decay / 6))
    ir = lp_fast(ir, 6000)
    ir /= np.abs(ir).sum() ** 0.5 * 4
    from scipy.signal import fftconvolve
    wet = fftconvolve(x, ir)[: len(x) + n]
    out = np.zeros(len(x) + n)
    out[: len(x)] += x * (1 - mix)
    out[: len(wet)] += wet * mix
    return out


def sfx(kind):
    if kind == "gunshot":
        n = int(SR * 0.6)
        noise = rng.standard_normal(n)
        crack = hp_fast(noise, 1500) * env(n, 0.0005, 0.03)
        body = lp_fast(noise, 900) * env(n, 0.001, 0.12) * 3
        t = np.arange(n) / SR
        thump = np.sin(2 * np.pi * 60 * t * np.exp(-t * 3)) * env(n, 0.001, 0.15) * 1.2
        x = crack * 1.4 + body + thump
        return reverb(x, 1.8, 0.35) * 0.9
    if kind == "crack":
        n = int(SR * 0.3)
        noise = rng.standard_normal(n)
        return reverb(hp_fast(noise, 2500) * env(n, 0.0003, 0.012) * 1.2, 1.0, 0.3) * 0.7
    if kind in ("whoosh", "swish", "rise"):
        dur = {"whoosh": 0.9, "swish": 0.35, "rise": 1.1}[kind]
        n = int(SR * dur)
        t = np.linspace(0, 1, n)
        shape = np.sin(np.pi * t) ** 2 if kind != "rise" else t ** 2 * (1 - t) * 6
        noise = rng.standard_normal(n)
        lo = bp_fast(noise, 300, 2500)
        return lo * shape * {"whoosh": 0.35, "swish": 0.22, "rise": 0.25}[kind]
    if kind == "impact":
        n = int(SR * 0.8)
        t = np.arange(n) / SR
        thump = np.sin(2 * np.pi * (45 + 80 * np.exp(-t * 30)) * t) * env(n, 0.001, 0.22)
        squelch = lp_fast(rng.standard_normal(n), 700) * env(n, 0.002, 0.08)
        return reverb(thump * 1.1 + squelch * 1.5, 1.2, 0.25) * 0.9
    if kind == "stretch":
        n = int(SR * 1.2)
        t = np.arange(n) / SR
        f = 35 + 25 * np.sin(2 * np.pi * 1.5 * t)
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.05, 0.5) * 0.6
    if kind == "gush":
        n = int(SR * 2.2)
        noise = lp_fast(rng.standard_normal(n), 500)
        mod = 0.6 + 0.4 * np.sin(2 * np.pi * 7 * np.arange(n) / SR)
        return noise * mod * env(n, 0.05, 0.9) * 1.3
    if kind == "shimmer":
        n = int(SR * 2.0)
        t = np.arange(n) / SR
        x = sum(np.sin(2 * np.pi * f * t) for f in (880, 1320, 1760, 2640)) / 4
        return x * env(n, 0.4, 0.8) * 0.12
    if kind == "heartbeat":
        out = np.zeros(int(SR * 0.6))
        for off, amp in ((0, 1.0), (0.17, 0.7)):
            n = int(SR * 0.25)
            t = np.arange(n) / SR
            b = np.sin(2 * np.pi * (50 + 30 * np.exp(-t * 25)) * t) * env(n, 0.003, 0.06) * amp
            i = int(off * SR)
            out[i:i + n] += b
        return out * 1.4
    if kind == "click":
        n = int(SR * 0.05)
        return hp_fast(rng.standard_normal(n), 3000) * env(n, 0.0005, 0.006) * 0.6
    if kind == "xray":
        n = int(SR * 2.5)
        t = np.arange(n) / SR
        x = np.sin(2 * np.pi * 120 * t) * 0.3 + bp_fast(rng.standard_normal(n), 3000, 6000) * 0.15
        return x * env(n, 0.3, 1.5) * 0.25
    raise ValueError(kind)


def music(total):
    """Dark, tense pad with a slow pulse, in A minor."""
    n = int(total * SR)
    t = np.arange(n) / SR
    chords = [(55.0, 82.41, 130.81), (43.65, 65.41, 130.81), (49.0, 73.42, 116.54), (41.2, 61.74, 123.47)]
    bar = 4.0
    x = np.zeros(n)
    for ci in range(int(total / bar) + 1):
        a, b = int(ci * bar * SR), min(n, int((ci + 1) * bar * SR + SR))
        if a >= n:
            break
        tt = t[a:b] - t[a]
        fade = np.minimum(1, tt / 0.8) * np.minimum(1, (tt[-1] - tt) / 0.8 + 1e-9)
        for f in chords[ci % len(chords)]:
            for det in (-0.6, 0.6):
                ph = 2 * np.pi * (f + det) * tt
                x[a:b] += (np.sin(ph) + 0.3 * np.sin(2 * ph) + 0.12 * np.sin(3 * ph)) * fade * 0.08
    # pulse: soft sub-kick every half second
    for k in np.arange(0, total, 0.5):
        i = int(k * SR)
        m = int(0.3 * SR)
        tt = np.arange(m) / SR
        kick = np.sin(2 * np.pi * (40 + 50 * np.exp(-tt * 40)) * tt) * np.exp(-tt / 0.09) * 0.25
        x[i:i + m] += kick[: max(0, min(m, n - i))]
    # high tension tick
    for k in np.arange(0.25, total, 0.5):
        i = int(k * SR)
        m = int(0.04 * SR)
        x[i:i + m] += hp_fast(rng.standard_normal(m), 5000)[: max(0, min(m, n - i))] * np.exp(-np.arange(m) / (SR * 0.008))[: max(0, min(m, n - i))] * 0.05
    x = lp_fast(x, 3000)
    fade = np.minimum(1, t / 1.0) * np.minimum(1, (total - t) / 1.5)
    return x * fade


def main():
    sc = T.scenes()
    total = (sc[-1]["start"] + sc[-1]["frames"]) / T.FPS + 0.5
    n = int(total * SR)
    vo = np.zeros(n)
    fx = np.zeros(n)
    for s in sc:
        v = load_vo(s["id"])
        i = int((s["start"] / T.FPS + T.VO_OFFSET) * SR)
        vo[i:i + len(v)] += v[: n - i]
    start = {s["id"]: s["start"] for s in sc}
    for sid, f, kind in T.events():
        x = sfx(kind)
        i = int((start[sid] + max(0, f - 1)) / T.FPS * SR)
        if i >= n:
            continue
        fx[i:i + len(x)] += x[: n - i]
    mus = music(total)
    # duck music under narration
    from scipy.ndimage import uniform_filter1d
    vo_env = uniform_filter1d(np.abs(vo), int(0.3 * SR))
    duck = 1 - 0.55 * np.clip(vo_env / (vo_env.max() * 0.15), 0, 1)
    vo = vo / np.abs(vo).max() * 0.85
    mix = vo + fx * 0.55 + mus * 0.35 * duck
    mix = np.tanh(mix * 1.1) / np.tanh(1.1)
    sf.write(os.path.join(T.ROOT, "audio", "mix.wav"), np.stack([mix, mix], 1).astype(np.float32), SR)
    print("audio length", total)


if __name__ == "__main__":
    main()
