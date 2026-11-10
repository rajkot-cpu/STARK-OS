"""Voiceover timeline: per-scene WAVs -> one narration track + a soft ambient pad."""
from __future__ import annotations

import math
import wave

import numpy as np

RATE = 44100
LEAD, GAP, TAIL = 0.35, 0.45, 0.9
MIN_SCENE = 2.5
CHORDS = [(220.0, 261.63, 329.63), (174.61, 220.0, 261.63), (196.0, 246.94, 293.66), (164.81, 207.65, 246.94)]


def read_wav(path: str) -> np.ndarray:
    with wave.open(path, "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError("expected 16-bit wav")
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        ch = w.getnchannels()
        if ch > 1:
            data = data.reshape(-1, ch).mean(axis=1)
        if w.getframerate() != RATE:
            n = int(len(data) * RATE / w.getframerate())
            data = np.interp(np.linspace(0, len(data) - 1, n), np.arange(len(data)), data).astype(np.float32)
    return data


def write_wav(path: str, data: np.ndarray) -> None:
    pcm = (np.clip(data, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


def timeline(clips: list[np.ndarray]) -> tuple[list[tuple[float, float]], float]:
    """Scene (start, duration) in seconds; each scene = its narration + a gap."""
    out, t = [], 0.0
    for i, c in enumerate(clips):
        d = len(c) / RATE + (LEAD if i == 0 else 0) + (GAP if i < len(clips) - 1 else TAIL)
        d = max(MIN_SCENE, d)
        out.append((t, d))
        t += d
    return out, t


def pad(total: float, scenes: list[tuple[float, float]], level: float = 0.05) -> np.ndarray:
    n = int(total * RATE)
    tt = np.arange(n, dtype=np.float32) / RATE
    out = np.zeros(n, dtype=np.float32)
    for k, (s, d) in enumerate(scenes):
        a, b = int(s * RATE), min(n, int((s + d) * RATE))
        seg = tt[a:b]
        for j, f in enumerate(CHORDS[k % len(CHORDS)]):
            out[a:b] += np.sin(2 * math.pi * f * seg + j) * (0.6 if j == 0 else 0.35)
            out[a:b] += np.sin(2 * math.pi * f * 0.5 * seg) * 0.25
    lfo = 0.75 + 0.25 * np.sin(2 * math.pi * 0.2 * tt)
    env = np.minimum(1.0, np.minimum(tt / 1.5, (total - tt) / 1.5)).clip(0, 1)
    peak = float(np.max(np.abs(out))) or 1.0
    return out / peak * level * lfo * env


def mix(clips: list[np.ndarray], with_pad: bool = True) -> tuple[np.ndarray, list[tuple[float, float]], float]:
    scenes, total = timeline(clips)
    n = int(total * RATE) + 1
    track = np.zeros(n, dtype=np.float32)
    for i, (c, (s, _d)) in enumerate(zip(clips, scenes)):
        a = int((s + (LEAD if i == 0 else 0)) * RATE)
        track[a:a + len(c)] += c[: max(0, n - a)]
    peak = float(np.max(np.abs(track))) or 1.0
    track = track / peak * 0.89
    if with_pad:
        track[: n - 1] += pad(total, scenes)
    return np.clip(track, -1, 1), scenes, total
