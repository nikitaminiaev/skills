#!/usr/bin/env python3
"""
Универсальная проверка CAD-сборки (build123d/OCP).
Скопируй в проект рядом со сборкой, заполни CONFIG, гоняй при каждом изменении геометрии.

Пять проверок:
  1. INTERFERENCE — попарно, ноль пересечений (кроме ALLOWED-контактов);
  2. FITS        — min-дистанция посадок против номинала;
  3. SUPPORT     — заявленные несущие контакты РЕАЛЬНО касаются (ловит «висящие» детали);
  4. LOCKS       — замок (байонет/фланец) держит: при малом осевом сдвиге без доворота
                   деталь упирается (ловит «лапка не в канавке», «замок не собран»);
  5. CHANNEL     — зонд-цилиндр вдоль оси луча/жгута/вала свободен кроме TRANSPARENT.

Сборка должна раздавать build_parts() -> {имя: Shape} в мировых координатах
(сложный узел — одной деталью-Compound).

Запуск:
  /path/to/venv/bin/python assembly_check.py <каталог-со--сборкой>

Заполняемые места — только раздел CONFIG ниже.
"""
import argparse
import importlib.util
import os
import sys
from build123d import Cylinder, Pos
from OCP.BRepExtrema import BRepExtrema_DistShapeShape

# ============================ CONFIG ============================
ASSEMBLY_MODULE = "assembly"   # файл со сборкой (assembly.py) в указанном каталоге
INT_TOL = 0.1                  # мм^3 пересечения без ALLOWED -> FAIL
BBOX_MARGIN = 2.0              # запас bbox-предфильтра, мм
TIGHT_TOL = 0.2                # зазор меньше номинала на это -> WARN "тесно"
LOOSE_TOL = 0.5                # зазор больше номинала на это -> WARN "болтается"

# Пары, которые СПЕЦИАЛЬНО соприкасаются/вложены (посадка по замыслу).
ALLOWED = set()

# Посадки: (имя1, имя2, номинал_мм, комментарий).
# Мерить ТОЛЬКО радиальные посадки без лицевого контакта (см. reference.md).
FITS = []

# Несущие контакты: (имя1, имя2, мин_площадь_мм2, что это). Проверка SUPPORT:
# площадь = макс. объём пересечения при сдвиге детали на 0.15 мм к партнёру / 0.15.
# Сюда — всё, на чём что-то стоит/лежит: плита→пьедестал, труба→держатель, …
SUPPORT = []

# Замки: (верхняя_деталь, нижняя_деталь, (dx,dy,dz) мм, что это). Проверка LOCKS:
# малый сдвиг вдоль оси снятия (0.5 мм) — пересечение > LOCK_MIN значит лапка/бурт
# упирается в канавку/стенку, т.е. замок собран. Для байонета, винтовых буртов.
LOCKS = []
LOCK_MIN = 0.3                 # мм^3: меньше — замок «не упирается»

# Трасса светового канала: (x, y, z0, z1) вдоль Z + радиус зонда + прозрачные тела.
CHANNEL_AXIS = None            # напр. (120, 120, 74, 419)
CHANNEL_R = 0.4
TRANSPARENT = []               # оптика/стекло/провод, напр. ["objective", "tube_lens"]
# ================================================================


def inter_volume(a, b):
    try:
        inter = a - (a - b)
    except Exception:
        return 0.0
    if inter is None:
        return 0.0
    try:
        return max(float(inter.volume), 0.0)
    except Exception:
        return 0.0


def boxes_touch(a, b, margin=BBOX_MARGIN):
    ba, bb = a.bounding_box(), b.bounding_box()
    return not (ba.max.X < bb.min.X - margin or bb.max.X < ba.min.X - margin or
                ba.max.Y < bb.min.Y - margin or bb.max.Y < ba.min.Y - margin or
                ba.max.Z < bb.min.Z - margin or bb.max.Z < ba.min.Z - margin)


def min_dist(a, b):
    dss = BRepExtrema_DistShapeShape(a.wrapped, b.wrapped)
    dss.Perform()
    return dss.Value()


def contact_area(a, b, probe=0.15):
    """Оценка площади контакта: макс. объём пересечения при сдвиге a на probe
    по ±X/±Y/±Z, делённый на probe."""
    best = 0.0
    for d in ((probe, 0, 0), (-probe, 0, 0), (0, probe, 0), (0, -probe, 0),
              (0, 0, probe), (0, 0, -probe)):
        best = max(best, inter_volume(Pos(*d) * a, b) / probe)
    return best


def check_interference(parts, report, counters):
    names = list(parts)
    pairs = 0
    for i, na in enumerate(names):
        for nb in names[i + 1:]:
            if frozenset([na, nb]) in ALLOWED or not boxes_touch(parts[na], parts[nb]):
                continue
            pairs += 1
            v = inter_volume(parts[na], parts[nb])
            if v > INT_TOL:
                counters["fail"] += 1
                report.append(f"  [FAIL] {na:20s} x {nb:20s} : {v:8.1f} мм^3")
    report.append(f"  проверено пар: {pairs}; пересечений > {INT_TOL} мм^3: {counters['fail']}")


def check_fits(parts, report, counters):
    for na, nb, expected, what in FITS:
        if na not in parts or nb not in parts:
            report.append(f"  [SKIP] {na} - {nb}: детали не найдены в сборке")
            continue
        d = min_dist(parts[na], parts[nb])
        tag = "[OK]"
        if d < expected - TIGHT_TOL:
            tag = "[WARN: тесно]"
            counters["warn"] += 1
        elif d > expected + LOOSE_TOL:
            tag = "[WARN: болтается]"
            counters["warn"] += 1
        report.append(f"  {na:20s} - {nb:20s} : {d:5.2f} мм (ждём {expected:.2f}) {what} {tag}")


def check_support(parts, report, counters):
    for na, nb, min_s, what in SUPPORT:
        if na not in parts or nb not in parts:
            report.append(f"  [SKIP] {na} - {nb}: детали не найдены в сборке")
            continue
        s = contact_area(parts[na], parts[nb])
        if s < min_s:
            counters["fail"] += 1
            report.append(f"  [FAIL] {na:20s} - {nb:20s} : S~{s:7.1f} мм^2 (мин {min_s}) {what}")
            continue
        report.append(f"  {na:20s} - {nb:20s} : S~{s:7.1f} мм^2 {what}  [OK]")


def check_locks(parts, report, counters):
    for a, b, d, what in LOCKS:
        if a not in parts or b not in parts:
            report.append(f"  [SKIP] {a} / {b}: детали не найдены в сборке")
            continue
        v = inter_volume(Pos(*d) * parts[a], parts[b])
        if v < LOCK_MIN:
            counters["fail"] += 1
            report.append(f"  [FAIL] {a:20s} / {b:20s} : сдвиг {d} -> V={v:.2f} мм^3 — замок не держит?")
            continue
        report.append(f"  {a:20s} / {b:20s} : сдвиг {d} -> V={v:6.2f} мм^3 {what}  [OK]")


def check_channel(parts, report, counters):
    if CHANNEL_AXIS is None:
        report.append("  CHANNEL_AXIS не задан — пропущено")
        return
    x, y, z0, z1 = CHANNEL_AXIS
    probe = Pos(x, y, (z0 + z1) / 2) * Cylinder(CHANNEL_R, z1 - z0)
    bad = 0
    for name, shape in parts.items():
        if name in TRANSPARENT or not boxes_touch(probe, shape, margin=1.0):
            continue
        v = inter_volume(probe, shape)
        if v > INT_TOL:
            bad += 1
            report.append(f"  [FAIL] трассе мешает: {name} ({v:.1f} мм^3)")
    if bad:
        counters["fail"] += 1
    else:
        report.append(f"  трасса (z {z0}..{z1}, X={x}, Y={y}) свободна")


def load_assembly(directory):
    path = os.path.join(directory, ASSEMBLY_MODULE + ".py")
    if not os.path.exists(path):
        sys.exit(f"Ошибка: не найден {ASSEMBLY_MODULE}.py в {directory}")
    sys.path.insert(0, directory)          # чтобы сборка видела соседние модули (gen_parts и т.п.)
    spec = importlib.util.spec_from_file_location(ASSEMBLY_MODULE, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[ASSEMBLY_MODULE] = mod
    spec.loader.exec_module(mod)
    if not hasattr(mod, "build_parts"):
        sys.exit("Ошибка: у сборки нет build_parts() -> {имя: Shape}")
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", nargs="?", default=os.path.dirname(os.path.abspath(__file__)))
    args = ap.parse_args()
    mod = load_assembly(args.dir)
    parts = mod.build_parts()
    counters = {"fail": 0, "warn": 0}
    report = []
    header = f"Проверка сборки: {len(parts)} тел, {len(ALLOWED)} разрешённых контактов"
    report.append(header)
    report.append("=" * len(header))

    report.append("\n[1] INTERFERENCE")
    report.append("-" * 30)
    check_interference(parts, report, counters)

    report.append("\n[2] FITS (min-зазор в посадках)")
    report.append("-" * 30)
    check_fits(parts, report, counters)

    report.append("\n[3] SUPPORT (несущие контакты реально касаются)")
    report.append("-" * 30)
    check_support(parts, report, counters)

    report.append("\n[4] LOCKS (замок держит без доворота)")
    report.append("-" * 30)
    check_locks(parts, report, counters)

    report.append("\n[5] CHANNEL (трасса вдоль оси)")
    report.append("-" * 30)
    check_channel(parts, report, counters)

    verdict = "FAIL" if counters["fail"] else ("WARN" if counters["warn"] else "PASS")
    report.append("=" * len(header))
    report.append(f"ИТОГ: {verdict}  (fail={counters['fail']}, warn={counters['warn']})")
    print("\n".join(report))
    return 1 if counters["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())