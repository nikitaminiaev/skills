#!/usr/bin/env python3
"""Сборка одного HTML-файла демонстрации из данных модели.

Вход — JSON вида:
    {
      "title": "...",                 # заголовок в шапке
      "manifest": {...},              # геометрия: детали, цвета, смещения в bin
      "frames":   {...},              # запечённые кадры: t + позы деталей
      "info":     {...},              # фазы, проверки, параметры
      "bin":      "<base64>"          # вершины/нормали/индексы
    }

Выход — самодостаточный HTML: three.js и OrbitControls вшиты, интернет не нужен.

Запуск:
    python build_demo.py model.json -o demo.html
    python build_demo.py model.json -o demo.html --max-mb 4

Проверки при сборке (мягкие — печатают WARN, жёсткие — падают):
    * все плейсхолдеры шаблона на месте;
    * в JSON нет ссылок http(s):// (демо должно работать офлайн);
    * итоговый файл не больше --max-mb;
    * JSON-блоки валидны после подстановки.
"""
import argparse
import base64
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
TPL = os.path.join(SKILL, "templates", "demo.html")
THREE = os.path.join(SKILL, "vendor", "three.min.js")
ORBIT = os.path.join(SKILL, "vendor", "OrbitControls.js")

PLACEHOLDERS = ("__TITLE__", "__MANIFEST__", "__FRAMES__", "__INFO__", "__BIN__")


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def esc_json(obj):
    """JSON для вставки внутрь <script type=application/json>."""
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return s.replace("</", "<\\/")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model", help="JSON с полями title/manifest/frames/info/bin")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--max-mb", type=float, default=4.0)
    args = ap.parse_args()

    data = json.loads(read(args.model))
    for key in ("manifest", "frames", "info", "bin"):
        if key not in data:
            sys.exit("в %s нет поля %s" % (args.model, key))

    tpl = read(TPL)
    missing = [p for p in PLACEHOLDERS if p not in tpl]
    if missing:
        sys.exit("в шаблоне нет плейсхолдеров: %s" % ", ".join(missing))

    html = tpl
    html = html.replace("/*THREE*/", read(THREE))
    html = html.replace("/*ORBIT*/", read(ORBIT))
    html = html.replace("__TITLE__", str(data.get("title", "Демонстрация")))
    html = html.replace("__MANIFEST__", esc_json(data["manifest"]))
    html = html.replace("__FRAMES__", esc_json(data["frames"]))
    html = html.replace("__INFO__", esc_json(data["info"]))

    raw = data["bin"]
    if isinstance(raw, str):
        raw_b64 = raw
        blob = base64.b64decode(raw)
    else:  # список байт — тоже допустимо
        blob = bytes(raw)
        raw_b64 = base64.b64encode(blob).decode("ascii")
    html = html.replace("__BIN__", raw_b64)

    # офлайн-проверка: внешних ссылок быть не должно
    ext = re.findall(r"(?:src|href)\s*=\s*[\"']https?://", html, re.I)
    if ext:
        print("WARN: в файле есть внешние ссылки (%d) — демо не будет работать офлайн" % len(ext))

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    size_mb = os.path.getsize(args.out) / 1048576.0
    print("wrote %s" % args.out)
    print("размер: %.2f МБ (bin %.1f КБ, треугольников ~%d)"
          % (size_mb, len(blob) / 1024.0, len(blob) // 12))
    if size_mb > args.max_mb:
        sys.exit("FAIL: файл больше %.1f МБ — уменьшите детализацию или число кадров" % args.max_mb)

    # контрольная проверка, что JSON читается обратно
    blocks = dict(re.findall(r'<script id="(manifest|frames|info)" type="application/json">(.*?)</script>',
                             html, re.S))
    for name, body in blocks.items():
        json.loads(body.replace("<\\/", "</"))
    print("JSON-блоки валидны: %s" % ", ".join(sorted(blocks)))


if __name__ == "__main__":
    main()
