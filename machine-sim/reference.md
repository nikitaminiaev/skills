# machine-sim — рабочие заготовки

Код проверен на mujoco 4.0.0 (Python 3.13), LinuxCNC 2.9.

## 1. MuJoCo: цапфа и чашка из примитивов

### Усечённый конус (цапфа) — только мешем

```python
import numpy as np

def frustum_vertices(r1, r2, h, n=24):
    """r1 — нижний радиус, r2 — верхний, h — высота; вернуть строку вершин в метрах."""
    v = []
    for k in range(n):
        a = 2 * np.pi * k / n
        v.append((r1 * np.cos(a), r1 * np.sin(a), 0.0))
    for k in range(n):
        a = 2 * np.pi * k / n
        v.append((r2 * np.cos(a), r2 * np.sin(a), h))
    return " ".join(f"{x/1000:.6f} {y/1000:.6f} {z/1000:.6f}" for x, y, z in v)
```

```xml
<asset>
  <mesh name="pin_cone" vertex="..."/>
</asset>
<body name="pin">
  <geom type="mesh" mesh="pin_cone" density="1240"/>
</body>
```

Отверстие в чашке одним телом не сделать: `box` — сплошной, цапфа ляжет на его
верхнюю грань. Чашка = кольцо (диск внутренней кромки) + поясок (пластины по
окружности) + раструб (наклонные боксы).

```python
def box_geom(name, size_mm, pos_mm, euler=(0, 0, 0), density=0.0):
    sx, sy, sz = (v / 1000 for v in size_mm)
    px, py, pz = (v / 1000 for v in pos_mm)
    return (f'<geom name="{name}" type="box" size="{sx} {sy} {sz}" '
            f'pos="{px} {py} {pz}" euler="{" ".join(map(str, euler))}" '
            f'density="{density}"/>')
```

### Замер качества контакта

```python
dmin = min(c.dist for c in data.contact[: data.ncon])   # < 0 — проникновение
assert abs(dmin) * 1000 <= 0.03, "контакт врёт: проникновение больше 0,03 мм"
```

Шаг и жёсткость:

```xml
<option timestep="0.0002" cone="elliptic" impratio="10" integrator="implicitfast"/>
```

- шаг 0,2–0,5 мс при зазоре 0,1–0,26 мм;
- `solref="0.004 1"` / `solimp="0.95 0.99 0.001"` подбирать по калибровке;
- мягкие контакты «просаживают» деталь — проверяй посадку по позе, а не по силе.

## 2. LinuxCNC: безголовый прогон

```bash
halrun -U >/dev/null 2>&1
pkill -f rtapi_app
Xvfb :71 -screen 0 1280x1024x24 &
DISPLAY=:71 linuxcnc machine.ini program.ngc >>run.log 2>&1 &
sleep 15
halcmd setp safety.script-reset 1; sleep 0.5
halcmd setp safety.script-reset 0
halcmd getp halui.program.is-running
```

- сброс E-stop: перезапустить watchdog (`enable-in 0 → 1`), затем `script-reset`;
- `halcmd setp` не работает на пине, подключённом к сигналу;
- `pkill -f "...[.]ini"` — иначе убьёшь свою оболочку;
- лог программы может быть пустым: диагностика — в отдельный файл.

## 3. G-код: захват

```
g1 z-30.37 f600
m62 p0            ; взять: выход переключится, когда станок доедет
g1 z0 f900
g0 x15 y73.5
g1 z-28.87 f600
m63 p0            ; отпустить — там же, где станок остановился
```

`M64/M65` — немедленные, интерпретатор ставит их раньше движения. Для
захвата/отпускания они не годятся.

## 4. Проверка плана против лимитов

```python
import json
plan = json.load(open("build_plan.json"))
for p in plan["parts"]:
    for key in ("pick_xy", "place_xy"):
        x, y = p[key]
        assert -45 <= x <= 45 and -92 <= y <= 98, (p["name"], key, x, y)
```
