"""Software 3D renderer (numpy + Pillow, CPU only, no GPU/driver needed).

Flat-shaded meshes with painter's-algorithm sorting, a perspective neon floor grid,
drifting particles, cheap bloom and fades. Each scene is rendered frame by frame
and streamed as raw RGB bytes to ffmpeg.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter


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
    def _grid_segments(self):
        if not hasattr(self, "_gseg"):
            a, b = [], []
            for i in range(-10, 11):
                a.append((i, 0, -10)); b.append((i, 0, 10))
            self._gseg_fixed = (np.array(a, np.float32), np.array(b, np.float32))
            self._gseg = True
        return self._gseg_fixed

    def _grid(self, draw, eye, R, t):
        col = np.clip(self.c1 * 0.55, 0, 255)
        y = -1.6
        off = (t * 0.8) % 1.0
        a1, b1 = self._grid_segments()
        zs = np.arange(-10, 11, dtype=np.float32) + off
        a2 = np.stack([np.full_like(zs, -10), np.zeros_like(zs), zs], 1)
        b2 = np.stack([np.full_like(zs, 10), np.zeros_like(zs), zs], 1)
        A = np.concatenate([a1, a2]) + np.array([0, y, 0], np.float32)
        B = np.concatenate([b1, b2]) + np.array([0, y, 0], np.float32)
        ca, cb = (A - eye) @ R.T, (B - eye) @ R.T
        near = 0.2
        keep = (ca[:, 2] >= near) | (cb[:, 2] >= near)
        ca, cb = ca[keep], cb[keep]
        s = np.clip((near - ca[:, 2]) / np.where(np.abs(cb[:, 2] - ca[:, 2]) < 1e-6, 1e-6, cb[:, 2] - ca[:, 2]), 0, 1)
        fa = ca[:, 2] < near
        ca[fa] = ca[fa] + (cb[fa] - ca[fa]) * s[fa, None]
        s2 = np.clip((near - cb[:, 2]) / np.where(np.abs(ca[:, 2] - cb[:, 2]) < 1e-6, 1e-6, ca[:, 2] - cb[:, 2]), 0, 1)
        fb = cb[:, 2] < near
        cb[fb] = cb[fb] + (ca[fb] - cb[fb]) * s2[fb, None]
        xa = np.stack([self.cx + self.f * ca[:, 0] / ca[:, 2], self.cy - self.f * ca[:, 1] / ca[:, 2]], 1)
        xb = np.stack([self.cx + self.f * cb[:, 0] / cb[:, 2], self.cy - self.f * cb[:, 1] / cb[:, 2]], 1)
        fade = np.clip(6.0 / np.maximum(np.minimum(ca[:, 2], cb[:, 2]), 0.1), 0.15, 1.0)
        lim = 4 * max(self.W, self.H)
        for p, q, k in zip(np.clip(xa, -lim, lim).tolist(), np.clip(xb, -lim, lim).tolist(), fade.tolist()):
            draw.line([tuple(p), tuple(q)], fill=tuple(int(c * k) for c in col), width=2)

    def _particles(self, draw, eye, R, t):
        pts = self.particles + np.array([0, (t * 0.25) % 8, 0], dtype=np.float32)
        pts[:, 1] = (pts[:, 1] + 3) % 8 - 3
        xy, z = self._project(pts, eye, R)
        base = self.c2 * 0.5 + 127
        ok = z >= 0.5
        r = np.maximum(1.0, 9.0 / np.maximum(z, 0.5))
        b = np.minimum(1.0, 5.0 / np.maximum(z, 0.5))
        for (x, y), rr, bb in zip(xy[ok].tolist(), r[ok].tolist(), b[ok].tolist()):
            draw.ellipse((x - rr, y - rr, x + rr, y + rr), fill=tuple(int(c * bb) for c in base))

    @staticmethod
    def _faces_array(o):
        if "F" not in o:
            o["F"] = np.array([f if len(f) == 4 else (f[0], f[1], f[2], f[2]) for f in o["faces"]], dtype=np.int32)
            o["tri"] = np.array([len(f) == 3 for f in o["faces"]])
        return o["F"], o["tri"]

    def frame(self, t: float, p: float) -> Image.Image:
        img = self.bg.copy()
        draw = ImageDraw.Draw(img)
        eye, R = self._camera(p)
        self._grid(draw, eye, R, t)
        self._particles(draw, eye, R, t)
        depths, pts_all, fills, edges, tris = [], [], [], [], []
        for o in self.objects:
            F, tri = self._faces_array(o)
            wv = self._obj_world(o, t, p)
            xy, z = self._project(wv, eye, R)
            # Diagonal cross: stays valid for sphere pole quads whose first two vertices coincide.
            n = np.cross(wv[F[:, 2]] - wv[F[:, 0]], wv[F[:, 3]] - wv[F[:, 1]])
            nn = np.linalg.norm(n, axis=1)
            good = nn > 1e-9
            n = n / np.where(good, nn, 1)[:, None]
            center = wv[F].mean(axis=1)
            view = eye - center
            facing = np.einsum("ij,ij->i", n, view)
            zf = z[F]
            mask = good & (zf.min(axis=1) >= 0.2)
            if not o.get("wire"):
                mask &= facing > 0
            if not mask.any():
                continue
            col = o["color"]
            lam = np.maximum(0.0, n @ self.light)
            rim = np.maximum(0.0, 1.0 - np.abs(facing) / (np.linalg.norm(view, axis=1) + 1e-6)) ** 2
            shade = np.clip(col[None, :] * (0.2 + 0.72 * lam[:, None]) + 90 * rim[:, None], 0, 255)
            if o.get("wire"):
                shade = shade * np.where(facing > 0, 0.35, 0.12)[:, None]
            edge = tuple(int(v) for v in np.clip(col * 0.6 + 110, 0, 255)) if o["outline"] else None
            idx = np.nonzero(mask)[0]
            depths.append(zf[idx].mean(axis=1))
            pts_all.append(xy[F[idx]])
            fills.append(shade[idx].astype(np.int32))
            edges.extend([edge] * len(idx))
            tris.append(tri[idx])
        if depths:
            D = np.concatenate(depths)
            P = np.concatenate(pts_all).tolist()
            C = np.concatenate(fills).tolist()
            T = np.concatenate(tris).tolist()
            for i in np.argsort(-D).tolist():
                pts = P[i][:3] if T[i] else P[i]
                e = edges[i]
                poly = [tuple(q) for q in pts]
                draw.polygon(poly, fill=tuple(C[i]))
                if e:
                    # NB: polygon(outline, width>1) pastes a full-frame mask per call in Pillow <12.
                    draw.line(poly + [poly[0]], fill=e, width=2)
        return self._bloom(img)

    def _bloom(self, img: Image.Image) -> Image.Image:
        small = img.reduce(6).filter(ImageFilter.GaussianBlur(4)).point(lambda v: v * 3 // 8)
        return ImageChops.add(img, small.resize(img.size, Image.BILINEAR))


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
            kk = max(0.0, k)
            yield img.point(lambda v: int(v * kk)).tobytes()
        else:
            yield img.tobytes()
