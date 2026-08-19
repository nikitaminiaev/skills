#!/usr/bin/env python3
"""Поиск через DuckDuckGo (ddgs). Использование: python3 ddg.py "<запрос>" [max_results] [region]"""
import json
import sys

from ddgs import DDGS


def main():
    if len(sys.argv) < 2:
        print("usage: python3 ddg.py <query> [max_results] [region]", file=sys.stderr)
        return 2

    query = sys.argv[1]
    max_results = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    region = sys.argv[3] if len(sys.argv) > 3 else "wt-wt"

    try:
        rows = DDGS().text(query, max_results=max_results, region=region)
    except Exception as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1

    if not rows:
        print(json.dumps({"error": "no results"}, ensure_ascii=False))
        return 1

    results = [
        {
            "title": row.get("title", ""),
            "href": row.get("href", ""),
            "body": (row.get("body") or "")[:300],
        }
        for row in rows
    ]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
