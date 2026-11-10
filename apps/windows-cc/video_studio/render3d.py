"""Software 3D renderer (numpy + Pillow, CPU only, no GPU/driver needed).

Flat-shaded meshes with painter's-algorithm sorting, a perspective neon floor grid,
drifting particles, cheap bloom and fades. Each scene is rendered frame by frame
and streamed as raw RGB bytes to ffmpeg.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def hex_rgb(h: str) -> np.ndarray:
    h = (h or "#ffffff").lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


# ---------------------------------------------------------------- meshes ----

def _mesh(verts, faces):
    return np.asarray(verts, dtype=np.float32), [tuple(f) for f in faces]


def cube():
    v = [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return _mesh(v, f)


def octahedron():
    v = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
    f = [(0, 2, 4), (2, 1, 4), (1, 3, 4), (3, 0, 4), (2, 0, 5), (1, 2, 5), (3, 1, 5), (0, 3, 5)]
    return _mesh(v, f)


def pyramid():
    v = [(-1, -0.8, -1), (1, -0.8, -1), (1, -0.8, 1), (-1, -0.8, 1), (0, 1.1, 0)]
    f = [(0, 1, 2, 3), (0, 4, 1), (1, 4, 2), (2, 4, 3), (3, 4, 0)]
    return _mesh(v, f)


def icosahedron():
    p = (1 + 5 ** 0.5) / 2
    v = [(-1, p, 0), (1, p, 0), (-1, -p, 0), (1, -p, 0), (0, -1, p), (0, 1, p), (0, -1, -p), (0, 1, -p),
         (p, 0, -1), (p, 0, 1), (-p, 0, -1), (-p, 0, 1)]
    v = [tuple(c / math.sqrt(1 + p * p) for c in x) for x in v]
    f = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
         (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5),
         (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    return _mesh(v, f)


def uv_sphere(seg=22, rings=14):
    v = []
    for i in range(rings + 1):
        th = math.pi * i / rings
        for j in range(seg):
            ph = 2 * math.pi * j / seg
            v.append((math.sin(th) * math.cos(ph), math.cos(th), math.sin(th) * math.sin(ph)))
    f = []
    for i in range(rings):
        for j in range(seg):
            a, b = i * seg + j, i * seg + (j + 1) % seg
            c, d = (i + 1) * seg + (j + 1) % seg, (i + 1) * seg + j
            f.append((a, b, c, d))
    return _mesh(v, f)


def torus(R=1.0, r=0.38, seg=30, sides=12):
    v = []
    for i in range(seg):
        u = 2 * math.pi * i / seg
        for j in range(sides):
            w = 2 * math.pi * j / sides
            v.append(((R + r * math.cos(w)) * math.cos(u), r * math.sin(w), (R + r * math.cos(w)) * math.sin(u)))
    f = []
    for i in range(seg):
        for j in range(sides):
            a = i * sides + j
            b = ((i + 1) % seg) * sides + j
            c = ((i + 1) % seg) * sides + (j + 1) % sides
            d = i * sides + (j + 1) % sides
            f.append((a, d, c, b))
    return _mesh(v, f)


_BASE = {"cube": cube, "octahedron": octahedron, "pyramid": pyramid, "icosahedron": icosahedron,
         "sphere": uv_sphere, "globe": lambda: uv_sphere(18, 10), "torus": torus}


def _rot(ax, ay, az):
    cx, sx, cy, sy, cz, sz = math.cos(ax), math.sin(ax), math.cos(ay), math.sin(ay), math.cos(az), math.sin(az)
    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], dtype=np.float32)
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=np.float32)
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], dtype=np.float32)
    return rz @ ry @ rx


def _ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


# --------------------------------------------------------------- scenes -----

class SceneRenderer:
    """Renders one scene (visual spec from script.parse_script) at a given size."""

    def __init__(self, visual: dict, width: int, height: int, seed: int = 0):
        self.v = visual
        self.W, self.H = int(width), int(height)
        self.rng = np.random.default_rng(seed + 7)
        self.c1 = hex_rgb(visual["colors"][0])
        self.c2 = hex_rgb(visual["colors"][1])
        self.f = min(self.W, self.H) * 1.25
        self.cx, self.cy = self.W / 2, self.H * (0.46 if self.H > self.W else 0.5)
        self.bg = self._background(hex_rgb(visual["background"][0]), hex_rgb(visual["background"][1]))
        self.objects = self._build_objects(visual["shape"])
        self.particles = self.rng.uniform([-7, -3, -7], [7, 5, 7], size=(140, 3)).astype(np.float32)
        self.light = np.array([0.45, 0.8, -0.55], dtype=np.float32)
        self.light /= np.linalg.norm(self.light)

    def _background(self, top, bottom) -> Image.Image:
        y = np.linspace(0, 1, self.H, dtype=np.float32)[:, None, None]
        grad = top[None, None, :] * (1 - y) + bottom[None, None, :] * y
        xx = np.linspace(-1, 1, self.W, dtype=np.float32)[None, :, None]
        yy = np.linspace(-1, 1, self.H, dtype=np.float32)[:, None, None]
        vign = 1.0 - 0.35 * np.clip(xx ** 2 + yy ** 2, 0, 1.6) / 1.6
        img = np.clip(np.broadcast_to(grad, (self.H, self.W, 3)) * vign, 0, 255).astype(np.uint8)
        return Image.fromarray(img, "RGB")

    def _build_objects(self, shape: str) -> list[dict]:
        objs = []
        if shape == "bars":
            n = 6
            heights = self.rng.uniform(0.6, 2.6, n)
            heights.sort() if self.rng.random() < 0.6 else None
            for i in range(n):
                verts, faces = cube()
                objs.append({"verts": verts, "faces": faces, "kind": "bar", "x": (i - (n - 1) / 2) * 0.75,
                             "h": float(heights[i]), "i": i, "n": n, "outline": True,
                             "color": self.c1 * (1 - i / (n - 1)) + self.c2 * (i / (n - 1))})
        elif shape == "rings":
            for i in range(3):
                verts, faces = torus(1.0 + 0.45 * i, 0.07, 40, 6)
                objs.append({"verts": verts, "faces": faces, "kind": "ring", "i": i, "outline": False,
                             "color": self.c1 if i % 2 == 0 else self.c2})
            verts, faces = uv_sphere(16, 10)
            objs.append({"verts": verts * 0.55, "faces": faces, "kind": "main", "outline": False, "color": self.c2})
        elif shape == "helix":
            verts, faces = cube()
            for strand in range(2):
                for i in range(16):
                    objs.append({"verts": verts * 0.16, "faces": faces, "kind": "helix", "i": i, "s": strand,
                                 "outline": False, "color": self.c1 if strand == 0 else self.c2})
        else:
            verts, faces = _BASE.get(shape, uv_sphere)()
            scale = {"cube": 1.0, "pyramid": 1.25, "torus": 1.25, "globe": 1.35, "sphere": 1.3}.get(shape, 1.45)
            objs.append({"verts": verts * scale, "faces": faces, "kind": "main",
                         "outline": shape in ("cube", "octahedron", "pyramid", "icosahedron", "globe"),
                         "wire": shape == "globe", "color": self.c1})
            sv, sf = icosahedron()
            for i in range(5):
                objs.append({"verts": sv * 0.2, "faces": sf, "kind": "sat", "i": i, "outline": True,
                             "color": self.c2})
        return objs

    # ---- camera ----
    def _camera(self, p: float):
        cam = self.v["camera"]
        az, el, dist, px = 0.35 + 1.4 * p, 0.28, 6.4, 0.0
        if cam == "zoom_in":
            dist, az = 9.0 - 3.6 * _ease(p), 0.4 + 0.5 * p
        elif cam == "zoom_out":
            dist, az = 4.6 + 3.8 * _ease(p), 0.9 - 0.5 * p
        elif cam == "pan":
            px, az = -1.8 + 3.6 * _ease(p), 0.25
        elif cam == "rise":
            el, az = -0.05 + 0.6 * _ease(p), 0.6 + 0.7 * p
        eye = np.array([px + dist * math.sin(az) * math.cos(el), dist * math.sin(el),
                        -dist * math.cos(az) * math.cos(el)], dtype=np.float32)
        target = np.array([px * 0.6, 0.0, 0.0], dtype=np.float32)
        fwd = target - eye
        fwd /= np.linalg.norm(fwd)
        right = np.cross(np.array([0, 1, 0], dtype=np.float32), fwd)
        right /= np.linalg.norm(right)
        up = np.cross(fwd, right)
        return eye, np.stack([right, up, fwd])

    def _project(self, pts, eye, R):
        cam = (pts - eye) @ R.T
        z = np.maximum(cam[:, 2], 0.05)
        return np.stack([self.cx + self.f * cam[:, 0] / z, self.cy - self.f * cam[:, 1] / z], axis=1), cam[:, 2]

    def _obj_world(self, o, t: float, p: float):
        motion = self.v.get("motion", "spin")
        k = o["kind"]
        if k == "bar":
            grow = _ease(p * 2.2 - o["i"] * 0.12)
            h = max(0.05, o["h"] * grow)
            v = o["verts"] * np.array([0.28, h / 2, 0.28], dtype=np.float32)
            return v + np.array([o["x"], -1.3 + h / 2, 0], dtype=np.float32)
        if k == "ring":
            R = _rot(0.9 + 0.3 * o["i"] + 0.4 * t, 0.6 * t * (1 + 0.3 * o["i"]), 0.2 * o["i"])
            return o["verts"] @ R.T
        if k == "helix":
            a = o["i"] * 0.55 + t * 1.2 + math.pi * o["s"]
            y = (o["i"] - 7.5) * 0.2
            c = np.array([math.cos(a) * 0.8, y, math.sin(a) * 0.8], dtype=np.float32)
            return o["verts"] @ _rot(t, t * 1.3, 0).T + c
        if k == "sat":
            a = t * 0.9 + o["i"] * 2 * math.pi / 5
            c = np.array([math.cos(a) * 2.5, 0.5 * math.sin(a * 1.7 + o["i"]), math.sin(a) * 2.5], dtype=np.float32)
            return o["verts"] @ _rot(t * 2, t * 1.5, 0).T + c
        # main
        R = _rot(0.35 + 0.25 * math.sin(t * 0.7), t * 0.8, 0.12 * math.sin(t * 0.5))
        v = o["verts"] @ R.T
        if motion == "pulse":
            v = v * (1.0 + 0.07 * math.sin(t * 4))
        elif motion == "float":
            v = v + np.array([0, 0.25 * math.sin(t * 1.6), 0], dtype=np.float32)
        return v

    # ---- drawing ----
    def _grid(self, draw, eye, R, t):
        col = tuple(int(c) for c in np.clip(self.c1 * 0.55, 0, 255))
        y = -1.6
        off = (t * 0.8) % 1.0
        segs = []
        for i in range(-10, 11):
            segs.append(((i, y, -10), (i, y, 10)))
        for j in range(-10, 11):
            z = j + off
            segs.append(((-10, y, z), (10, y, z)))
        for a, b in segs:
            pts = np.array([a, b], dtype=np.float32)
            cam = (pts - eye) @ R.T
            if cam[0, 2] < 0.2 and cam[1, 2] < 0.2:
                continue
            if cam[0, 2] < 0.2 or cam[1, 2] < 0.2:  # clip to near plane
                s = (0.2 - cam[0, 2]) / (cam[1, 2] - cam[0, 2])
                pc = cam[0] + (cam[1] - cam[0]) * s
                if cam[0, 2] < 0.2:
                    cam[0] = pc
                else:
                    cam[1] = pc
            xy = [(self.cx + self.f * c[0] / c[2], self.cy - self.f * c[1] / c[2]) for c in cam]
            depth = float(min(cam[:, 2]))
            fade = max(0.15, min(1.0, 6.0 / max(depth, 0.1)))
            draw.line(xy, fill=tuple(int(c * fade) for c in col), width=2)

    def _particles(self, draw, eye, R, t):
        pts = self.particles + np.array([0, (t * 0.25) % 8, 0], dtype=np.float32)
        pts[:, 1] = (pts[:, 1] + 3) % 8 - 3
        xy, z = self._project(pts, eye, R)
        base = self.c2 * 0.5 + 127
        for (x, y), d in zip(xy, z):
            if d < 0.5:
                continue
            r = max(1.0, 9.0 / d)
            b = min(1.0, 5.0 / d)
            draw.ellipse((x - r, y - r, x + r, y + r), fill=tuple(int(c * b) for c in base))

    def frame(self, t: float, p: float) -> Image.Image:
        img = self.bg.copy()
        draw = ImageDraw.Draw(img)
        eye, R = self._camera(p)
        self._grid(draw, eye, R, t)
        self._particles(draw, eye, R, t)
        polys = []
        for o in self.objects:
            wv = self._obj_world(o, t, p)
            xy, z = self._project(wv, eye, R)
            col = o["color"]
            edge = tuple(int(c) for c in np.clip(col * 0.6 + 110, 0, 255))
            for f in o["faces"]:
                idx = list(f)
                a, b, c = wv[idx[0]], wv[idx[1]], wv[idx[2]]
                n = np.cross(b - a, c - a)
                nn = float(np.linalg.norm(n))
                if nn < 1e-9:
                    continue
                n = n / nn
                center = wv[idx].mean(axis=0)
                view = eye - center
                facing = float(np.dot(n, view))
                if facing <= 0 and not o.get("wire"):
                    continue
                if min(z[i] for i in idx) < 0.2:
                    continue
                lam = max(0.0, float(np.dot(n, self.light)))
                rim = max(0.0, 1.0 - abs(facing) / (float(np.linalg.norm(view)) + 1e-6)) ** 2
                shade = np.clip(col * (0.22 + 0.78 * lam) + 90 * rim, 0, 255)
                if o.get("wire"):
                    shade = shade * (0.35 if facing > 0 else 0.12)
                polys.append((float(np.mean([z[i] for i in idx])), [tuple(xy[i]) for i in idx],
                              tuple(int(c) for c in shade), edge if o["outline"] else None))
        polys.sort(key=lambda q: -q[0])
        for _, pts, fill, edge in polys:
            draw.polygon(pts, fill=fill, outline=edge, width=2 if edge else 0)
        return self._bloom(img)

    def _bloom(self, img: Image.Image) -> Image.Image:
        small = img.resize((self.W // 6, self.H // 6), Image.BILINEAR).filter(ImageFilter.GaussianBlur(4))
        glow = np.asarray(small.resize((self.W, self.H), Image.BILINEAR), dtype=np.uint16)
        base = np.asarray(img, dtype=np.uint16)
        out = np.minimum(base + (glow * 3 >> 3), 255).astype(np.uint8)
        return Image.fromarray(out, "RGB")


def render_scene_frames(visual: dict, width: int, height: int, seconds: float, fps: int, seed: int = 0,
                        t0: float = 0.0, fade: float = 0.3):
    """Yield raw RGB bytes for every frame of one scene."""
    sr = SceneRenderer(visual, width, height, seed)
    n = max(1, int(round(seconds * fps)))
    nf = max(1, int(fade * fps))
    for i in range(n):
        t = t0 + i / fps
        img = sr.frame(t, i / max(1, n - 1))
        k = min(1.0, (i + 1) / nf, (n - i) / nf)
        if k < 1.0:
            arr = (np.asarray(img, dtype=np.float32) * k).astype(np.uint8)
            yield arr.tobytes()
        else:
            yield img.tobytes()
