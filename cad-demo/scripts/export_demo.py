#!/usr/bin/env python3
"""Экспорт CAD-сборки build123d в данные для HTML-демонстрации.

Модуль сборки должен отдавать `build_parts() -> dict[str, Shape]` в мировых
координатах (контракт cad-assembly-check) и может дополнительно определить:

    DEMO = {                       # всё необязательное
        "title": "Цикл стыковки",
        "subtitle": "кубик 30 мм",
        "duration": 12.0,
        "colors":  {"cubeA": "#9aa3ad"},     # цвет детали
        "labels":  {"cubeA": "Кубик A"},     # подпись в легенде
        "groups":  {"cubeA": "A"},           # произвольная группировка
        "checks":  [{"name": "F входа", "value": "0,9 Н", "ok": True}],
        "params":  {"Габарит": "30×30×30 мм"},
        "phases":  [{"t0": 0, "t1": 2.5, "name": "Подвод", "note": "..."}],
    }

    def demo_rest() -> dict:      # поза детали при t=0, если не identity
        return {"cubeB": {"p": [0,0,0], "q": [0,0,0,1]}}

    def demo_frames() -> dict:    # запечённые кадры
        return {"t": [0.0, 0.1, ...],
                "parts": {"cubeB": {"p": [[..],..], "q": [[..],..]}}}

Геометрия всегда запекается в мировых координатах при t=0; позы кадров —
абсолютные, вьюер сам считает переход от t=0. Поэтому `demo_rest()` нужен
только если деталь в t=0 уже сдвинута.

Запуск:
    python export_demo.py путь/к/gen_x.py -o model.json [--tol 0.15] [--angle 0.25]
Затем:
    python build_demo.py model.json -o demo.html
"""
import argparse
import base64
import importlib.util
import json
import math
import os
import struct
import sys

from build123d import Shape


# ---------------------------------------------------------------- тесселяция
def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _norm(v):
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (v[0] / n, v[1] / n, v[2] / n) if n > 1e-12 else (0.0, 0.0, 1.0)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def tessellate(shape: Shape, tol: float, ang: float, smooth_deg: float = 38.0):
    """Треугольники с расщеплением вершин по рёбрам жёсткости.

    Возвращает (positions, normals, indices) в мировых координатах.
    Плоские грани остаются плоскими (CAD-вид), цилиндры сглаживаются:
    соседние треугольники одной вершины объединяются в кластер, пока угол
    между их нормалями меньше smooth_deg.
    """
    verts, tris = shape.tessellate(tol, ang)
    P = [(v.X, v.Y, v.Z) for v in verts]

    tri_n = []
    for (a, b, c) in tris:
        tri_n.append(_norm(_cross(_sub(P[b], P[a]), _sub(P[c], P[a]))))

    inc = {}                       # вершина -> список треугольников
    for ti, (a, b, c) in enumerate(tris):
        for vi in (a, b, c):
            inc.setdefault(vi, []).append(ti)

    cos_lim = math.cos(math.radians(smooth_deg))
    out_p, out_n = [], []
    vert_of = {}                   # (треугольник, исходная вершина) -> новая вершина

    for vi, tlist in inc.items():
        clusters = []              # [сумма нормалей, [треугольники], индекс вершины]
        for ti in tlist:
            n = tri_n[ti]
            for cl in clusters:
                if _dot(_norm(cl[0]), n) >= cos_lim:
                    cl[0] = (cl[0][0] + n[0], cl[0][1] + n[1], cl[0][2] + n[2])
                    cl[1].append(ti)
                    break
            else:
                clusters.append([n, [ti], -1])
        for cl in clusters:
            new_i = len(out_p)
            out_p.append(P[vi])
            out_n.append(_norm(cl[0]))
            for ti in cl[1]:
                vert_of[(ti, vi)] = new_i

    idx = []
    for ti, (a, b, c) in enumerate(tris):
        idx.extend((vert_of[(ti, a)], vert_of[(ti, b)], vert_of[(ti, c)]))
    return out_p, out_n, idx


# ---------------------------------------------------------------- упаковка
def pack_part(shape: Shape, tol: float, ang: float, smooth: float):
    P, N, I = tessellate(shape, tol, ang, smooth)
    if not I:
        raise SystemExit("деталь без треугольников — пустая геометрия")
    lo = [min(p[k] for p in P) for k in range(3)]
    hi = [max(p[k] for p in P) for k in range(3)]
    scale = [(hi[k] - lo[k]) / 65535.0 if hi[k] > lo[k] else 1e-6 for k in range(3)]

    # позиции: квантуем в 0..65535 и сдвигаем на -32768, чтобы знаковый int16
    # покрывал весь диапазон без SpecialCase-веток при чтении
    qp = bytearray()
    for p in P:
        for k in range(3):
            q = int(round((p[k] - lo[k]) / scale[k]))
            q = max(0, min(65535, q))
            qp += struct.pack("<h", q - 32768)
    qn = bytearray()
    for n in N:
        for k in range(3):
            v = int(round(n[k] * 127))
            qn += struct.pack("<b", max(-127, min(127, v)))
    qi = bytearray()
    for i in I:
        qi += struct.pack("<I", i)
    return dict(nv=len(P), nt=len(I) // 3, pos=bytes(qp), nrm=bytes(qn), idx=bytes(qi),
                lo=lo, scale=scale)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("module", help="путь к gen_*.py со сборкой")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--tol", type=float, default=0.15, help="допуск тесселяции, мм")
    ap.add_argument("--angle", type=float, default=0.25, help="угловой допуск, рад")
    ap.add_argument("--smooth", type=float, default=38.0, help="порог сглаживания, градусы")
    ap.add_argument("--parts", default="", help="подмножество деталей через запятую")
    args = ap.parse_args()

    spec = importlib.util.spec_from_file_location("demo_mod", args.module)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["demo_mod"] = mod
    spec.loader.exec_module(mod)

    parts = mod.build_parts()
    if not isinstance(parts, dict) or not parts:
        sys.exit("build_parts() должен вернуть непустой dict")

    want = [s.strip() for s in args.parts.split(",") if s.strip()]
    names = want or list(parts)
    missing = [n for n in names if n not in parts]
    if missing:
        sys.exit("нет деталей: %s (есть: %s)" % (", ".join(missing), ", ".join(parts)))

    meta = dict(getattr(mod, "DEMO", {}) or {})
    colors = meta.get("colors", {})
    labels = meta.get("labels", {})
    groups = meta.get("groups", {})
    default_colors = ["#8d99ae", "#d4a017", "#2a9d8f", "#c0566b", "#5c6bc0", "#6a994e",
                      "#e07a3f", "#7b4ea3", "#3c8dad", "#a8763e"]

    blob = bytearray()
    manifest = {"parts": {}, "order": []}
    for i, name in enumerate(names):
        pk = pack_part(parts[name], args.tol, args.angle, args.smooth)
        off_pos = len(blob)
        blob += pk["pos"]
        off_nrm = len(blob)
        blob += pk["nrm"]
        while len(blob) % 4:
            blob.append(0)
        off_idx = len(blob)
        blob += pk["idx"]
        manifest["parts"][name] = {
            "label": labels.get(name, name),
            "group": groups.get(name, ""),
            "color": colors.get(name, default_colors[i % len(default_colors)]),
            "nv": pk["nv"], "nt": pk["nt"],
            "off_pos": off_pos, "off_nrm": off_nrm, "off_idx": off_idx,
            "lo": pk["lo"], "scale": pk["scale"],
            "volume_mm3": round(parts[name].volume, 1) if hasattr(parts[name], "volume") else None,
        }
        manifest["order"].append(name)

    frames = mod.demo_frames() if hasattr(mod, "demo_frames") else {}
    if not frames:
        frames = {"t": [0.0], "parts": {}}
    rest = dict(mod.demo_rest() if hasattr(mod, "demo_rest") else {})

    # Геометрия запечена в мировых координатах, а кадры задают абсолютную позу.
    # Чтобы вьюер не применил позу дважды, опорой считаем позу из первого кадра.
    for name, tr in (frames.get("parts") or {}).items():
        if name not in manifest["parts"]:
            continue
        p0 = tr["p"][0] if tr.get("p") else [0.0, 0.0, 0.0]
        q0 = tr["q"][0] if tr.get("q") else [0.0, 0.0, 0.0, 1.0]
        rest[name] = {"p": list(p0), "q": list(q0)}

    for name, r in rest.items():
        if name in manifest["parts"]:
            manifest["parts"][name]["rest"] = r

    info = {
        "title": meta.get("title", os.path.basename(args.module)),
        "subtitle": meta.get("subtitle", ""),
        "duration": meta.get("duration", (frames.get("t") or [1])[-1]),
        "phases": meta.get("phases", []),
        "checks": meta.get("checks", []),
        "params": meta.get("params", {}),
    }

    model = {"title": info["title"], "manifest": manifest, "frames": frames,
             "info": info, "bin": base64.b64encode(bytes(blob)).decode("ascii")}

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False, separators=(",", ":"))

    tris = sum(p["nt"] for p in manifest["parts"].values())
    print("wrote %s: деталей %d, треугольников %d, bin %.1f КБ"
          % (args.out, len(names), tris, len(blob) / 1024.0))


if __name__ == "__main__":
    main()
