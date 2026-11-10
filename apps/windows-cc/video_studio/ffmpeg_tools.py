"""Find (or download once into jarvis\\tools\\ffmpeg) an ffmpeg build with libass, and wrap calls."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

DOWNLOADS = [
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JarvisVideoStudio/1"
_NOWIN = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW


class FFmpegMissing(RuntimeError):
    pass


def _exe(name: str) -> str:
    return name + (".exe" if sys.platform == "win32" else "")


def _has_subtitles(ffmpeg: str) -> bool:
    try:
        out = subprocess.run([ffmpeg, "-hide_banner", "-filters"], capture_output=True, text=True,
                             timeout=20, creationflags=_NOWIN).stdout
    except Exception:
        return False
    return " subtitles " in out


def locate(root: Path) -> tuple[str, str] | None:
    env = os.environ.get("JARVIS_FFMPEG", "").strip()
    cands = []
    if env:
        cands.append((env, str(Path(env).with_name(_exe("ffprobe")))))
    tdir = Path(root) / "tools" / "ffmpeg" / "bin"
    cands.append((str(tdir / _exe("ffmpeg")), str(tdir / _exe("ffprobe"))))
    w, p = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if w and p:
        cands.append((w, p))
    for ff, fp in cands:
        if Path(ff).is_file() and Path(fp).is_file() and _has_subtitles(ff):
            return ff, fp
    return None


def ensure(root: Path, progress=None) -> tuple[str, str]:
    """Return (ffmpeg, ffprobe); download a static Windows build on first use."""
    found = locate(root)
    if found:
        return found
    if sys.platform != "win32":
        raise FFmpegMissing("ffmpeg with libass not found (install ffmpeg)")
    tdir = Path(root) / "tools" / "ffmpeg"
    tdir.mkdir(parents=True, exist_ok=True)
    errors = []
    for url in DOWNLOADS:
        zpath = tdir / "ffmpeg-download.zip"
        try:
            if progress:
                progress("downloading ffmpeg (one time, ~100 MB)")
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r, open(zpath, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                got, last = 0, -1
                while True:
                    buf = r.read(1 << 20)
                    if not buf:
                        break
                    f.write(buf)
                    got += len(buf)
                    pct = int(got * 100 / total) if total else -1
                    if progress and pct >= 0 and pct // 10 != last:
                        last = pct // 10
                        progress(f"downloading ffmpeg {pct}%")
            bindir = tdir / "bin"
            bindir.mkdir(exist_ok=True)
            with zipfile.ZipFile(zpath) as z:
                for n in z.namelist():
                    base = n.rsplit("/", 1)[-1].lower()
                    if base in ("ffmpeg.exe", "ffprobe.exe"):
                        with z.open(n) as src, open(bindir / base, "wb") as dst:
                            shutil.copyfileobj(src, dst)
            zpath.unlink(missing_ok=True)
            found = locate(root)
            if found:
                return found
            errors.append(f"{url}: no usable ffmpeg in archive")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{url}: {type(e).__name__}: {str(e)[:120]}")
            try:
                zpath.unlink(missing_ok=True)
            except Exception:
                pass
    raise FFmpegMissing("could not get ffmpeg: " + "; ".join(errors))


class FFmpeg:
    def __init__(self, ffmpeg: str, ffprobe: str):
        self.ffmpeg, self.ffprobe = ffmpeg, ffprobe

    def run(self, args: list[str], cwd: str | None = None, timeout: float = 600) -> None:
        r = subprocess.run([self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y"] + args, cwd=cwd,
                           capture_output=True, text=True, timeout=timeout, creationflags=_NOWIN)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg failed ({r.returncode}): {r.stderr.strip()[-400:]}")

    def to_wav(self, src: str, dst: str, rate: int = 44100) -> None:
        self.run(["-i", src, "-ac", "1", "-ar", str(rate), "-c:a", "pcm_s16le", dst])

    def open_encoder(self, out_dir: str, width: int, height: int, fps: int, audio: str, subs: str | None,
                     fontsdir: str | None, out_name: str = "video.mp4",
                     out_size: tuple[int, int] | None = None) -> subprocess.Popen:
        vf = []
        if out_size and tuple(out_size) != (width, height):
            vf.append(f"scale={out_size[0]}:{out_size[1]}:flags=lanczos")
        if subs:
            f = f"subtitles=filename={subs}"
            if fontsdir:
                f += f":fontsdir={fontsdir}"
            vf.append(f)
        args = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
                "-i", audio]
        if vf:
            args += ["-vf", ",".join(vf)]
        args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", out_name]
        return subprocess.Popen(args, cwd=out_dir, stdin=subprocess.PIPE, stderr=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, creationflags=_NOWIN)

    def thumbnail(self, video: str, at: float, dst: str) -> None:
        self.run(["-ss", f"{at:.2f}", "-i", video, "-frames:v", "1", dst])

    def probe(self, path: str) -> dict:
        r = subprocess.run([self.ffprobe, "-v", "error", "-show_entries",
                            "format=duration,size:stream=codec_type,codec_name,width,height",
                            "-of", "json", path], capture_output=True, text=True, timeout=60,
                           creationflags=_NOWIN)
        if r.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {r.stderr.strip()[-300:]}")
        j = json.loads(r.stdout or "{}")
        fmt = j.get("format") or {}
        return {"duration": float(fmt.get("duration") or 0), "size": int(fmt.get("size") or 0),
                "streams": [{k: s.get(k) for k in ("codec_type", "codec_name", "width", "height") if s.get(k)}
                            for s in j.get("streams") or []]}
