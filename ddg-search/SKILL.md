---
name: ddg-search
description: Запасной веб-поиск через DuckDuckGo. Используй, когда встроенный websearch вернул ошибку (403/EOF/сбой сети) или пустой результат, либо когда нужен поиск без VPN из РФ. Работает через MCP-инструмент duckduckgo_search (если он есть в окружении) или через python-библиотеку ddgs. Триггеры: «websearch не работает», «поиск без VPN», «duckduckgo_search», «найди в интернете».
---

# Запасной веб-поиск через DuckDuckGo

Встроенный `websearch` может быть недоступен из РФ (403/EOF). Запасной вариант — DuckDuckGo.

## Алгоритм (выполняй по порядку)

1. **Проверь доступные инструменты.** Посмотри в списке своих tools/MCP. Если есть `duckduckgo_search` — используй его:
   - Аргументы: `query` (обязательно), опционально `max_results` (по умолчанию 10), `region` (`wt-wt`, `ru-ru`).
   - Для чтения страницы по URL используй `duckduckgo_fetch_content` (`url`, `max_length`, `start_index`). Никогда не открывай `file://` и локальные пути.
   - Если MCP-поиск вернул пусто или ошибку — переходи к шагу 2.

2. **MCP нет или не сработал — используй установленную python-библиотеку `ddgs`** через скрипт в папке скилла:

   python3 /home/nikita/.config/opencode/skills/ddg-search/ddg.py "<запрос>" max_results region

Пример:
   python3 /home/nikita/.config/opencode/skills/ddg-search/ddg.py "последние новости ИИ 2026" 5 ru-ru

Скрипт выводит JSON-массив с `title`, `href`, `body`.

## Примечания

- Перед первым использованием проверь, что пакет установлен: `python3 -c "from ddgs import DDGS"`. Если `ModuleNotFoundError` — установи его в тот же python: `python3 -m pip install --user ddgs` (или `--break-system-packages` на Debian при externally-managed).
- Задержку между запросами библиотека делает сама — не добавляй паузы.
- Пустой результат или ошибка `anomaly/blocked` — повтори запрос с другой формулировкой, поменяй регион или уменьши `max_results`.
- Не пытайся заменить поиск через `webfetch` на `html.duckduckgo.com`/`lite.duckduckgo.com` — из РФ они отдают антикапчу (anomaly), это проверено.
- Найденные страницы читай обычным `webfetch` по `href`.
