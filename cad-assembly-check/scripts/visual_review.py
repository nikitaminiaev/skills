#!/usr/bin/env python3
"""
Листы визуальной ревью CAD-сборки для агента (PNG, matplotlib Agg, без GPU).

Дополняет числовые проверки assembly_check.py «другой модальностью»: сгенерированные
листы читает агент (vision) и ищет то, что числа не видят — деталь не на месте,
стык не входит в стык, тракт перекрыт, деталь «висит» или «утонула».

Сборка должна раздавать build_parts() -> {имя: Shape} в мировых координатах
(тот же контракт, что у assembly_check.py).

Три листа в OUT_DIR:
  visual_assembly.png  — изометрии + ортографии + изо со световой трассой
  visual_parts.png     — каждая деталь отдельной панелью (имя, габарит, объём)
  visual_sections.png  — clip-разрезы (убрана ближняя половина) + линии сечения

ЗАПУСКАТЬ из каталога сборки (или передать dir):
  /path/to/venv/bin/python visual_review.py [каталог-со-сборкой]

Заполняемые места — только раздел CONFIG ниже.
"""
import argparse
import importlib.util
import math
import os
import sys

import numpy as np
import trimesh
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection

# ============================ CONFIG ============================
ASSEMBLY_MODULE = "assembly"   # файл со сборкой (assembly.py) рядом

# Окраска по группам: (метка легенды, цвет, кортеж подстрок имени).
# Первая же группа, чья подстрока встретилась в имени, и красит деталь.
GROUPS = [
    ("рама/плиты", "#8d99ae", ("bottom_plate", "top_plate", "stud", "nut")),
    ("оптика", "#3a86ff", ("objective", "lens", "optics")),
    ("корпус", "#2a9d8f", ("housing", "engine")),
    ("корпусное/прочее", "#b0b0b0", ("",)),  # подстрока "" матсит всё — только последней
]

# Изометрии для листа сборки: (заголовок, elev, azim).
ISOMETRICS = [
    ("iso azim -60", 25, -60),
    ("iso azim -150", 25, -150),
    ("iso azim 120", 25, 120),
    ("iso azim 30", 25, 30),
]
# Ортографии: (заголовок, elev, azim).
ORTHOGRAPHICS = [
    ("front (XZ)", 2, -90),
    ("side (YZ)", 2, 180),
    ("top (XY)", 89, -90),
]

# Световая трасса: список 3D-точек, ломаная поверх последнего изо-вьюера. None — пропуск.
# Должна совпадать с probe-check в assembly_check.py.
LIGHT_POLYLINE = [(120, 120, 74), (120, 120, 358), (45, 120, 358)]
LIGHT_COLOR = "#ffd500"

# Clip-разрезы: (заголовок, ось 0=X/1=Y/2=Z, позиция, keep_below, elev, azim).
# keep_below=True оставляет часть с координатой < позиции (ближняя к камере убирается).
CUTS = [
    ("clip y>0, вид с −Y", 1, 120.0, False, 2, -90),
    ("clip y<0, вид с +Y", 1, 120.0, True, 2, 90),
]

MAX_FACES = None  # decimate цель на деталь; None = полная сетка
OUT_DIRNAME = "preview"   # каталог листов: _resurses/preview если есть, иначе <dir>/preview
# ================================================================

LIGHT_VEC = np.array([0.4, -0.5, 0.75])
LIGHT_VEC = LIGHT_VEC / np.linalg.norm(LIGHT_VEC)


def color_of(name):
    for label, hexcolor, patterns in GROUPS:
        for p in patterns:
            if p in name:
                return hexcolor
    return "#b0b0b0"


def load_assembly(directory):
    path = os.path.join(directory, ASSEMBLY_MODULE + ".py")
    if not os.path.exists(path):
        sys.exit(f"Ошибка: не найден {ASSEMBLY_MODULE}.py в {directory}")
    sys.path.insert(0, directory)
    spec = importlib.util.spec_from_file_location(ASSEMBLY_MODULE, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[ASSEMBLY_MODULE] = mod
    spec.loader.exec_module(mod)
    if not hasattr(mod, "build_parts"):
        sys.exit("Ошибка: у сборки нет build_parts() -> {имя: Shape}")
    return mod.build_parts()


def part_mesh(shape, max_faces=MAX_FACES):
    verts, faces = shape.tessellate(1.0)
    verts = np.array([(v.X, v.Y, v.Z) for v in verts], dtype=float)
    faces = np.asarray(faces, dtype=np.int32)
    if max_faces and len(faces) > max_faces:
        m = trimesh.Trimesh(verts, faces, process=False)
        m = m.simplify_quadric_decimation(face_count=max_faces)
        return np.asarray(m.vertices), np.asarray(m.faces)
    return verts, faces


def shaded_colors(tris, hexcolor):
    import matplotlib.colors as mcolors

    base = np.array(mcolors.to_rgb(hexcolor))
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    lam = np.divide(n, np.maximum(ln, 1e-12)) @ LIGHT_VEC
    k = (0.45 + 0.55 * np.clip(lam, 0, 1))[:, None]
    return np.clip(base[None, :] * k, 0, 1)


def add_part(ax, tris, hexcolor, edge="none", lw=0.1):
    pc = Poly3DCollection(tris, facecolors=shaded_colors(tris, hexcolor),
                          edgecolors=edge, linewidths=lw)
    ax.add_collection3d(pc)


def fit_bounds(meshes, pad=0.04):
    v = np.vstack([m[0] for m in meshes.values()])
    lo, hi = v.min(axis=0), v.max(axis=0)
    span = (hi - lo) * pad / 2
    return lo - span, hi + span


def set_view(ax, lo, hi, elev, azim, ticks=True):
    ax.set_xlim(lo[0], hi[0]); ax.set_ylim(lo[1], hi[1]); ax.set_zlim(lo[2], hi[2])
    ax.set_box_aspect((hi - lo).tolist())
    ax.view_init(elev=elev, azim=azim)
    ax.set_proj_type("ortho")
    if not ticks:
        ax.set_xticks([]); ax.set_yticks([]); ax.set_zticks([])
        ax.grid(False)
        for pane in (ax.xaxis, ax.yaxis, ax.zaxis):
            pane.pane.set_visible(False)


def clip_tris(tris, axis, value, keep_below):
    c = tris.mean(axis=1)[:, axis]
    return tris[c <= value] if keep_below else tris[c >= value]


def section_outlines(meshes, axis, value):
    origin = [0.0, 0.0, 0.0]
    origin[axis] = value
    normal = [0.0, 0.0, 0.0]
    normal[axis] = 1.0
    lines = []
    for verts, faces in meshes.values():
        try:
            path = trimesh.Trimesh(verts, faces, process=False).section(
                plane_origin=origin, plane_normal=normal)
        except Exception:
            continue
        if path is None or not len(path.entities):
            continue
        for line in path.discrete:
            if len(line) > 1:
                lines.append(np.asarray(line))
    return lines


def sheet_assembly(meshes, out_path):
    views = list(ISOMETRICS) + list(ORTHOGRAPHICS)
    ncol = 4
    nrow = math.ceil((len(views) + 1) / ncol)  # +1: изо с трассой
    fig = plt.figure(figsize=(4.4 * ncol, 3.9 * nrow))
    lo, hi = fit_bounds(meshes)
    for i, (title, elev, azim) in enumerate(views, 1):
        ax = fig.add_subplot(nrow, ncol, i, projection="3d")
        for name, (verts, faces) in meshes.items():
            add_part(ax, verts[faces], color_of(name))
        set_view(ax, lo, hi, elev, azim)
        ax.set_title(title, fontsize=10)
    ax = fig.add_subplot(nrow, ncol, len(views) + 1, projection="3d")
    for name, (verts, faces) in meshes.items():
        add_part(ax, verts[faces], color_of(name))
    set_view(ax, lo, hi, *ISOMETRICS[0][1:])
    if LIGHT_POLYLINE:
        pts = [list(map(float, p)) for p in LIGHT_POLYLINE]
        segs = [pts[i:i + 2] for i in range(len(pts) - 1)]
        ax.add_collection3d(Line3DCollection(segs, colors=LIGHT_COLOR, linewidths=3.0))
        ax.scatter(*pts[0], c=LIGHT_COLOR, s=40, zorder=11)
        ax.set_title("iso + световая трасса", fontsize=10)
    handles = [Patch(facecolor=c, label=l) for l, c, _ in GROUPS]
    if LIGHT_POLYLINE:
        handles.append(Patch(facecolor=LIGHT_COLOR, label="световая трасса"))
    fig.legend(handles=handles, loc="lower center", ncol=len(handles),
               fontsize=8, frameon=False)
    fig.suptitle(f"Сборка: {len(meshes)} тел — визуальная ревью", fontsize=13)
    fig.tight_layout(rect=(0, 0.04, 1, 0.96))
    fig.savefig(out_path, dpi=110)
    plt.close(fig)


def sheet_parts(meshes, shapes, out_path):
    names = list(shapes)
    ncol = 7
    nrow = math.ceil(len(names) / ncol)
    fig = plt.figure(figsize=(18, 2.6 * nrow))
    for i, name in enumerate(names, 1):
        ax = fig.add_subplot(nrow, ncol, i, projection="3d")
        verts, faces = meshes[name]
        tris = verts[faces]
        add_part(ax, tris, color_of(name), edge="#333333", lw=0.15)
        lo, hi = verts.min(axis=0), verts.max(axis=0)
        d = hi - lo
        pad = max(d) * 0.04
        set_view(ax, lo - pad, hi + pad, 25, -60, ticks=False)
        ax.set_title(f"{name}\n{d[0]:.0f}×{d[1]:.0f}×{d[2]:.0f} мм · {shapes[name].volume:.0f} мм³",
                     fontsize=7.5)
    fig.suptitle("Штучный лист: каждая деталь — своей панелью (габарит, объём)", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.985))
    fig.savefig(out_path, dpi=110)
    plt.close(fig)


def sheet_sections(meshes, out_path):
    fig = plt.figure(figsize=(6.2 * len(CUTS), 6))
    lo, hi = fit_bounds(meshes)
    for col, (title, axis, value, keep_below, elev, azim) in enumerate(CUTS, 1):
        ax = fig.add_subplot(1, len(CUTS), col, projection="3d")
        for name, (verts, faces) in meshes.items():
            tris = clip_tris(verts[faces], axis, value, keep_below)
            if len(tris):
                add_part(ax, tris, color_of(name))
        lines = section_outlines(meshes, axis, value)
        if lines:
            ax.add_collection3d(Line3DCollection(lines, colors="black", linewidths=0.8))
        set_view(ax, lo, hi, elev, azim)
        ax.set_title(title, fontsize=10)
    fig.suptitle("Clip-разрезы: внутренности тракта (линии сечения чёрным)", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(out_path, dpi=110)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", nargs="?", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--max-faces", type=int, default=MAX_FACES,
                    help="decimate цель на деталь (0 = полная сетка)")
    args = ap.parse_args()

    parts = load_assembly(args.dir)
    cap = args.max_faces or None
    meshes = {name: part_mesh(shape, cap) for name, shape in parts.items()}
    resurses = os.path.join(args.dir, "_resurses")
    out = os.path.join(resurses, "preview") if os.path.isdir(resurses) \
        else os.path.join(args.dir, OUT_DIRNAME)
    os.makedirs(out, exist_ok=True)
    total = sum(len(f) for _, f in meshes.values())
    print(f"{args.dir}: {len(parts)} тел, {total} граней")

    sheet_assembly(meshes, os.path.join(out, "visual_assembly.png"))
    sheet_parts(meshes, parts, os.path.join(out, "visual_parts.png"))
    sheet_sections(meshes, os.path.join(out, "visual_sections.png"))
    print("листы в", out)


if __name__ == "__main__":
    main()
