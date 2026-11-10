#!/usr/bin/env python3
"""Высококачественные виды CAD-сборки для агента и человека.

Зачем. `visual_review.py` рисует matplotlib-ом: треугольники сортируются по
глубине (painter's algorithm), z-буфера нет — пересекающиеся детали
«просвечивают», тонкие зазоры врут. Здесь рендер идёт через WebGL (three.js)
в headless Chrome: настоящий z-буфер, MSAA, тени, контуры. Плюс свободный
зум: любой ракурс, любая точка, любой размер кадра, clip-плоскость,
изоляция деталей, призрак остального.

Два режима:
  * PNG для агента — `--sheet` (сетка видов) или одиночный вид с `--target`,
    `--size`, `--azim`, `--elev`, `--clip`, `--only`, `--hide`, `--ghost`;
  * интерактивный HTML для человека — `--html`: орбита, зум, клип, изоляция,
    камера в URL-хэше (`#t=x,y,z&d=60&az=35&el=25`).

Контракт сцены — словарь:
    {"title": "машина", "bodies": [
        {"name": "нога A слой 1", "shape": <build123d Shape>,
         "key": "01 short structural", "group": "machine",
         "color": (185, 190, 198)}, ...]}

Можно не писать свой загрузчик: `--assembly модуль` вызовет
`build_parts() -> {имя: Shape}` (контракт cad-assembly-check), а
`--scene модуль:функция` возьмёт готовый словарь сцены.

Примеры:

    # лист 3×2 и интерактивный файл
    python render_views.py --scene cad.view_scene:build_scene --group machine \
        --sheet --html --out _resurses/out/cad/view/machine_v4

    # зум на узел: имя, ракурс, поле 60 мм, разрез
    python render_views.py --scene cad.view_scene:build_scene \
        --only "нога A*" --ghost --size 80 --azim 30 --elev 20 --clip z=-260 \
        --labels --out _resurses/out/cad/view/machine_v4/zoom_leg.png

    # пачка видов за один запуск (сборка и сетки — один раз)
    python render_views.py --scene cad.view_scene:build_scene \
        --batch cad.view_scene:SHOTS --out _resurses/out/cad/view/machine_v4

Тяжёлое: сборка и тесселяция. Запускать в фоне с taskset/OMP, как в
проекте; рендер одного кадра — 1–5 с.
"""

from __future__ import annotations

import argparse
import base64
import fnmatch
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
VENDOR = HERE.parent / "vendor"
TEMPLATE = HERE / "view_template.html"
CHROME = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")

# Палитра для чужих сборок: цвет по ключу, а не по порядку.
PALETTE = (
    "#8fa9c4", "#c49a6c", "#8fbf7f", "#c47f9a", "#9b8fc4",
    "#c4b26c", "#6cb2b8", "#b8b8b8", "#c47f6c", "#7f9ac4",
    "#a6c46c", "#c46cb2",
)


# --- данные сцены ----------------------------------------------------------

@dataclass
class Body:
    name: str
    shape: object
    key: str = ""
    group: str = ""
    color: str = "#b8b8b8"


@dataclass
class Scene:
    title: str = "assembly"
    bodies: list[Body] = field(default_factory=list)

    def select(self, only=(), hide=(), group=None) -> "Scene":
        out = []
        for b in self.bodies:
            if group and b.group != group:
                continue
            if only and not any(fnmatch.fnmatchcase(b.name, p) for p in only):
                continue
            if hide and any(fnmatch.fnmatchcase(b.name, p) for p in hide):
                continue
            out.append(b)
        return Scene(self.title, out)


def as_hex(color) -> str:
    if isinstance(color, str):
        return color
    r, g, b = (int(round(v)) for v in color)
    return f"#{r:02x}{g:02x}{b:02x}"


def scene_from_dict(data: dict) -> Scene:
    bodies = []
    for i, b in enumerate(data.get("bodies", [])):
        color = b.get("color", PALETTE[i % len(PALETTE)])
        bodies.append(Body(
            name=str(b["name"]), shape=b["shape"],
            key=str(b.get("key", "")), group=str(b.get("group", "")),
            color=as_hex(color),
        ))
    return Scene(str(data.get("title", "assembly")), bodies)


def scene_from_parts(parts: dict, title: str = "assembly") -> Scene:
    bodies = []
    for i, (name, shape) in enumerate(parts.items()):
        key = name.split()[0] if name.split() else name
        bodies.append(Body(name=name, shape=shape, key=key,
                           group="", color=PALETTE[i % len(PALETTE)]))
    return Scene(title, bodies)


# --- тесселяция ------------------------------------------------------------

def mesh_shape(shape, angular: float = 0.08, tolerance: float = 0.1):
    """Треугольники тела. `angular` — главный регулятор качества.

    В build123d 0.11 `tessellate(tol)` переиспользует уже готовую сетку,
    поэтому перед съёмом чистим триангуляцию и мешим заново с нужным
    угловым допуском. Проверено: ang=0.5 → 500 треугольников на цилиндр,
    ang=0.05 → 1000, ang=0.02 → 2500.
    """
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRepTools import BRepTools

    wrapped = getattr(shape, "wrapped", None)
    if wrapped is None:
        return np.zeros((0, 3), np.float32), np.zeros((0,), np.uint32)

    BRepTools.Clean_s(wrapped)
    BRepMesh_IncrementalMesh(wrapped, tolerance, False, angular, True)
    verts, tris = shape.tessellate(tolerance, angular)
    if not verts or not tris:
        return np.zeros((0, 3), np.float32), np.zeros((0,), np.uint32)

    pos = np.array([(v.X, v.Y, v.Z) for v in verts], dtype=np.float32)
    idx = np.array(tris, dtype=np.uint32).reshape(-1)
    return pos, idx


def b64(arr: np.ndarray) -> str:
    return base64.b64encode(arr.tobytes()).decode("ascii")


# Кэш сеток: лист рисует 6 видов одной сцены, и без кэша каждая смена
# ракурса мешает все 280 тел заново (это минуты). Ключ — сам объект Shape
# и угловой допуск.
_MESH_CACHE: dict[tuple[int, float], tuple[np.ndarray, np.ndarray]] = {}


def cached_mesh(shape, angular: float):
    key = (id(shape), angular)
    hit = _MESH_CACHE.get(key)
    if hit is None:
        hit = mesh_shape(shape, angular=angular)
        _MESH_CACHE[key] = hit
    return hit


def body_json(body: Body, angular: float) -> dict | None:
    pos, idx = cached_mesh(body.shape, angular)
    if len(pos) == 0 or len(idx) == 0:
        return None
    lo = pos.min(axis=0)
    hi = pos.max(axis=0)
    return {
        "name": body.name,
        "key": body.key,
        "group": body.group,
        "color": body.color,
        "center": ((lo + hi) / 2).tolist(),
        "bbox": [*lo.tolist(), *hi.tolist()],
        "pos": b64(pos),
        "idx": b64(idx),
        "tris": int(len(idx) // 3),
    }


def model_json(scene: Scene, angular: float, context_angular: float,
               selected: set[str]) -> dict:
    bodies = []
    for b in scene.bodies:
        # Выбранные детали — мелко, контекст — грубо: зум не тонет в миллионах
        # треугольников, но нужный узел виден гладко.
        ang = angular if b.name in selected else context_angular
        item = body_json(b, ang)
        if item is not None:
            bodies.append(item)
    return {"title": scene.title, "bodies": bodies}


# --- вид и камера ----------------------------------------------------------

@dataclass
class View:
    name: str = "view"
    target: tuple[float, float, float] | None = None
    size: float | None = None
    az: float = 35.0
    el: float = 25.0
    ortho: bool = True
    clip: tuple[str, float, bool] | None = None
    only: tuple[str, ...] = ()
    hide: tuple[str, ...] = ()
    ghost: bool = False
    labels: bool = False
    inset: bool = False
    zoom_box: tuple[float, ...] | None = None
    bg: tuple[int, int, int] = (242, 244, 247)
    width: int = 2000
    height: int = 1400
    angular: float = 0.08
    context_angular: float = 0.25

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "target": list(self.target) if self.target else None,
            "size": self.size,
            "az": self.az,
            "el": self.el,
            "ortho": self.ortho,
            "clip": list(self.clip) if self.clip else None,
            "only": list(self.only),
            "hide": list(self.hide),
            "ghost": self.ghost,
            "labels": self.labels,
            "inset": self.inset,
            "bg": list(self.bg),
            "width": self.width,
            "height": self.height,
        }


def scene_bbox(scene: Scene) -> tuple[np.ndarray, np.ndarray]:
    lo = np.array([np.inf, np.inf, np.inf])
    hi = np.array([-np.inf, -np.inf, -np.inf])
    for b in scene.bodies:
        bb = b.shape.bounding_box()
        lo = np.minimum(lo, [bb.min.X, bb.min.Y, bb.min.Z])
        hi = np.maximum(hi, [bb.max.X, bb.max.Y, bb.max.Z])
    return lo, hi


def fit_view(scene: Scene, view: View) -> View:
    """Достроить target/size по выбранным деталям, если их не задали.

    Поле кадра считается по проекции габарита на экран, а не по максимальной
    стороне bbox: у машины 815 мм идут вдоль Z (вбок), а вверх — 443 мм,
    поэтому max-сторона оставляла бы полкадра пустым.
    """
    sel = scene.select(view.only, view.hide)
    if not sel.bodies:
        sel = scene
    lo, hi = scene_bbox(sel)
    center = (lo + hi) / 2
    size3 = hi - lo
    if view.target is None:
        view.target = tuple(float(v) for v in center)
    if view.size is not None:
        return view

    az, el = np.radians(view.az), np.radians(view.el)
    d = np.array([np.cos(el) * np.sin(az), np.sin(el), np.cos(el) * np.cos(az)])
    right = np.cross(d, np.array([0.0, 1.0, 0.0]))
    if np.linalg.norm(right) < 1e-9:
        right = np.array([1.0, 0.0, 0.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, d)
    half_v = 0.5 * float(np.sum(size3 * np.abs(up)))
    half_h = 0.5 * float(np.sum(size3 * np.abs(right)))
    aspect = max(view.width / max(view.height, 1), 0.1)
    span = 2.0 * max(half_v, half_h / aspect)
    view.size = span * 1.18 if span > 0 else 100.0
    return view


# --- HTML и скриншот -------------------------------------------------------

def build_html(scene: Scene, view: View, selected: set[str],
               out_html: Path, model: dict | None = None) -> Path:
    model = model or model_json(scene, view.angular, view.context_angular, selected)
    template = TEMPLATE.read_text(encoding="utf-8")
    three = (VENDOR / "three.min.js").read_text(encoding="utf-8")
    orbit = (VENDOR / "OrbitControls.js").read_text(encoding="utf-8")
    html = (template
            .replace("__TITLE__", scene.title)
            .replace("__THREE__", three)
            .replace("__ORBIT__", orbit)
            .replace("__MODEL__", json.dumps(model, separators=(",", ":")))
            .replace("__VIEW__", json.dumps(view.to_json(), separators=(",", ":"))))
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html, encoding="utf-8")
    return out_html


def screenshot(html: Path, out_png: Path, width: int, height: int,
               budget_ms: int = 400) -> None:
    if CHROME is None:
        raise SystemExit("нет google-chrome/chromium — рендер невозможен")
    out_png.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        CHROME, "--headless=new", "--disable-gpu", "--use-angle=swiftshader",
        "--hide-scrollbars", "--force-device-scale-factor=1",
        "--no-sandbox", "--disable-dev-shm-usage",
        f"--window-size={width},{height}",
        f"--virtual-time-budget={budget_ms}",
        "--run-all-compositor-stages-before-draw",
        f"--screenshot={out_png}",
        f"file://{html}?shot=1",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out_png.exists():
        raise RuntimeError(
            f"chrome вернул {proc.returncode}\n{proc.stderr[-2000:]}")
    if out_png.stat().st_size < 1000:
        raise RuntimeError(f"пустой скриншот: {out_png}")


def render(scene: Scene, view: View, out_png: Path,
           keep_html: bool = False) -> Path:
    view = fit_view(scene, view)
    # Мелкая сетка — только явно выбранным телам (`--only`). Иначе весь лист
    # мешится мелко и рендер шести видов занимает минуты.
    selected = ({b.name for b in scene.select(view.only, view.hide).bodies}
                if view.only else set())
    tmp = Path(tempfile.mkdtemp(prefix="cadview_"))
    try:
        html = build_html(scene, view, selected, tmp / "view.html")
        t0 = time.time()
        screenshot(html, out_png, view.width, view.height)
        print(f"  {out_png.name}: {view.width}×{view.height}, "
              f"{out_png.stat().st_size / 1024:.0f} КБ, {time.time() - t0:.1f} с")
        if keep_html:
            html_out = out_png.with_suffix(".html")
            shutil.copyfile(html, html_out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out_png


# --- лист видов ------------------------------------------------------------

SHEET = (
    ("изометрия", 35.0, 25.0, None),
    ("изометрия сзади", -145.0, 25.0, None),
    ("спереди", 0.0, 0.0, None),
    ("сбоку", 90.0, 0.0, None),
    ("сверху", 0.0, 89.0, None),
    ("разрез Z=0", 35.0, 25.0, ("z", 0.0, False)),
)


def compose_sheet(tiles: list[Path], titles: list[str], out_png: Path,
                  cols: int = 3, gap: int = 12, footer: str = "") -> None:
    from PIL import Image, ImageDraw, ImageFont

    imgs = [Image.open(p).convert("RGB") for p in tiles]
    w, h = imgs[0].size
    rows = (len(imgs) + cols - 1) // cols
    head = 34
    sheet = Image.new("RGB", (cols * w + (cols + 1) * gap,
                              rows * (h + head) + (rows + 1) * gap + (28 if footer else 0)),
                      (232, 235, 239))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    except OSError:
        font = small = ImageFont.load_default()

    for i, (img, title) in enumerate(zip(imgs, titles)):
        r, c = divmod(i, cols)
        x = gap + c * (w + gap)
        y = gap + r * (h + head + gap)
        draw.text((x + 4, y + 5), title, fill=(27, 32, 38), font=font)
        sheet.paste(img, (x, y + head))
    if footer:
        draw.text((gap + 4, sheet.height - 24), footer, fill=(90, 100, 110), font=small)
    sheet.save(out_png)


def render_sheet(scene: Scene, out_dir: Path, group: str | None,
                 width: int, height: int, angular: float,
                 context_angular: float) -> Path:
    base = scene.select(group=group) if group else scene
    base_view = fit_view(base, View())
    tiles, titles = [], []
    tmp = Path(tempfile.mkdtemp(prefix="cadsheet_"))
    try:
        for name, az, el, clip in SHEET:
            view = View(name=name, target=base_view.target, size=None,
                        az=az, el=el, clip=clip, width=width, height=height,
                        angular=angular, context_angular=context_angular)
            tile = tmp / f"{len(tiles)}.png"
            print(f"  лист: {name}")
            render(base, view, tile)
            tiles.append(tile)
            titles.append(name)
        lo, hi = scene_bbox(base)
        footer = (f"{base.title} · {len(base.bodies)} тел · "
                  f"габарит {hi[0]-lo[0]:.0f} × {hi[1]-lo[1]:.0f} × {hi[2]-lo[2]:.0f} мм")
        out = out_dir / "sheet.png"
        compose_sheet(tiles, titles, out, footer=footer)
        print(f"  лист: {out}")
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- CLI -------------------------------------------------------------------

def parse_vec(text: str) -> tuple[float, ...]:
    return tuple(float(v) for v in text.replace(";", ",").split(","))


def parse_clip(text: str) -> tuple[str, float, bool]:
    parts = text.split(":")
    axis = parts[0].lower()
    if axis not in ("x", "y", "z"):
        raise SystemExit(f"clip: ось должна быть x/y/z, а не {axis!r}")
    pos = float(parts[1]) if len(parts) > 1 and parts[1] else 0.0
    flip = len(parts) > 2 and parts[2] in ("1", "flip", "true")
    return axis, pos, flip


def load_scene(args) -> Scene:
    root = Path.cwd()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    if args.scene:
        mod_name, _, fn = args.scene.partition(":")
        mod = importlib.import_module(mod_name)
        data = getattr(mod, fn or "build_scene")()
        if isinstance(data, Scene):
            return data
        return scene_from_dict(data)
    if args.assembly:
        mod = importlib.import_module(args.assembly)
        parts = mod.build_parts()
        return scene_from_parts(parts, title=args.assembly)
    raise SystemExit("нужен --scene модуль:функция или --assembly модуль")


def render_batch(scene: Scene, specs: list[dict], out_dir: Path, defaults,
                 default_group: str | None = None) -> None:
    """Пачка видов за один запуск: сборка и сетки считаются один раз.

    Спека — JSON-список; поля как у CLI, но в camel-виде `azim/elev`,
    `only/hide` — списки glob, `clip` — строка `"z=-260"` или `[ось, поз, flip]`.
    `group` в спеке переопределяет группу для этого вида (`""` — вся сцена).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for spec in specs:
        out = Path(spec.get("out") or f"{spec.get('name', 'view')}.png")
        if not out.is_absolute():
            out = out_dir / out
        group = spec.get("group", default_group)
        base = scene.select(group=group) if group else scene
        clip = spec.get("clip")
        if isinstance(clip, str):
            clip = parse_clip(clip)
        elif clip:
            clip = tuple(clip)
        view = View(
            name=out.stem,
            target=tuple(spec["target"]) if spec.get("target") else None,
            size=spec.get("size"),
            az=float(spec.get("azim", defaults.azim)),
            el=float(spec.get("elev", defaults.elev)),
            clip=clip,
            only=tuple(spec.get("only", ())),
            hide=tuple(spec.get("hide", ())),
            ghost=bool(spec.get("ghost", False)),
            labels=bool(spec.get("labels", False)),
            inset=bool(spec.get("inset", False)),
            width=int(spec.get("width", defaults.width)),
            height=int(spec.get("height", defaults.height)),
            angular=float(spec.get("angular", defaults.angular)),
            context_angular=float(spec.get("context_angular", defaults.context_angular)),
        )
        print(f"вид {view.name}")
        render(base, view, out)


def load_batch(text: str) -> list[dict]:
    """Спека пачки: JSON-файл или `модуль:ИМЯ` со списком в Python."""
    path = Path(text)
    if path.exists() or text.endswith(".json"):
        return json.loads(path.read_text(encoding="utf-8"))
    mod_name, _, attr = text.partition(":")
    if not attr:
        raise SystemExit(f"--batch: нет файла {text!r} и не указан модуль:ИМЯ")
    return getattr(importlib.import_module(mod_name), attr)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scene", help="модуль:функция, возвращает словарь сцены")
    p.add_argument("--assembly", help="модуль с build_parts()")
    p.add_argument("--group", help="только эта группа тел (machine/storage)")
    p.add_argument("--out", required=True, help="PNG или каталог")
    p.add_argument("--sheet", action="store_true", help="лист 3×2")
    p.add_argument("--html", action="store_true", help="интерактивный HTML всей сцены")
    p.add_argument("--batch", help="JSON-список видов: отрендерить пачкой за один запуск")
    p.add_argument("--target", type=parse_vec, help="центр кадра x,y,z")
    p.add_argument("--size", type=float, help="поле кадра по большей стороне, мм")
    p.add_argument("--azim", type=float, default=35.0)
    p.add_argument("--elev", type=float, default=25.0)
    p.add_argument("--clip", type=parse_clip, help="x=100 / y=0:flip")
    p.add_argument("--only", action="append", default=[], help="glob имён: оставить")
    p.add_argument("--hide", action="append", default=[], help="glob имён: скрыть")
    p.add_argument("--ghost", action="store_true", help="остальное — призраком")
    p.add_argument("--labels", action="store_true", help="подписи имён")
    p.add_argument("--inset", action="store_true", help="врезка общего вида")
    p.add_argument("--width", type=int, default=2000)
    p.add_argument("--height", type=int, default=1400)
    p.add_argument("--angular", type=float, default=0.08,
                   help="угловой допуск сетки выбранных тел (меньше — глаже)")
    p.add_argument("--context-angular", type=float, default=0.25,
                   help="угловой допуск сетки контекста")
    p.add_argument("--budget", type=int, default=400,
                   help="виртуальное время Chrome, мс")
    args = p.parse_args()

    t0 = time.time()
    full = load_scene(args)
    scene = full.select(group=args.group) if args.group else full
    print(f"сцена {scene.title}: {len(scene.bodies)} тел")

    out = Path(args.out)
    if args.sheet:
        out.mkdir(parents=True, exist_ok=True)
        render_sheet(scene, out, args.group, args.width, args.height,
                     args.angular, args.context_angular)
    if args.html:
        # HTML — вся сцена целиком и грубой сеткой: 280 тел мелкой сеткой
        # дают файл в сотни мегабайт, а человеку хватает силуэта.
        out.mkdir(parents=True, exist_ok=True)
        html_angular = max(args.context_angular, 0.6)
        view = fit_view(full, View(name="обзор", az=args.azim, el=args.elev,
                                   width=args.width, height=args.height,
                                   angular=html_angular,
                                   context_angular=html_angular,
                                   ghost=args.ghost, labels=args.labels,
                                   inset=args.inset))
        html = build_html(full, view, set(), out / "view.html")
        print(f"  HTML: {html}")
    if args.batch:
        out_dir = out if out.suffix.lower() != ".png" else out.parent
        specs = load_batch(args.batch)
        render_batch(full, specs, out_dir, args, args.group)
    if not args.sheet and not args.html and not args.batch:
        view = View(
            name=out.stem, target=args.target, size=args.size,
            az=args.azim, el=args.elev, clip=args.clip,
            only=tuple(args.only), hide=tuple(args.hide),
            ghost=args.ghost, labels=args.labels, inset=args.inset,
            width=args.width, height=args.height,
            angular=args.angular, context_angular=args.context_angular,
        )
        if out.suffix.lower() != ".png":
            out = out / f"{view.name}.png"
        render(scene, view, out)
    print(f"готово за {time.time() - t0:.1f} с")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
