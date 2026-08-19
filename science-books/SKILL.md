---
name: science-books
description: Local scientific books knowledge base with search and download. Host: http://192.168.0.153:8000/
---

# Science Books — scientific books knowledge base

Host: `http://192.168.0.153:8000/`

## Available endpoints

### Search books

```
GET /api/search?q={query}&limit=20&offset=0
```

**Parameters:**
- `q` — search query (required)
- `limit` — results per page (default 20)
- `offset` — pagination offset (default 0)

**Example via curl:**
```bash
curl --fail --location 'http://192.168.0.153:8000/api/search?q=quantum+mechanics&limit=5'
```

**Example via webfetch:**
```
http://192.168.0.153:8000/api/search?q=quantum+mechanics&limit=5
```

### Download file

```
GET /api/file/{md5}
```

**Parameters:**
- `md5` — MD5 hash of the file from search results

**Example:**
```bash
curl --fail --location --output '/tmp/opencode/book.pdf' 'http://192.168.0.153:8000/api/file/abc123def456...'
```

### Extract text from PDF (optional)

```bash
pdftotext '/tmp/opencode/book.pdf' '/tmp/opencode/book.txt'
```

## Typical workflow

1. Search for a book via `/api/search` with the desired query
2. Pick a result, note its `md5`
3. Download the file via `/api/file/{md5}`

## Download policy

Не стесняться скачивать книги в `/tmp/opencode/` для исследования текущего вопроса — это штатный способ сверить утверждения заметок с первоисточниками. Скачивание в `/tmp/opencode/` разрешено и в plan mode (read-only для рабочей директории, но не для временной). После скачивания извлечь текст `pdftotext` и искать по нему; при необходимости указать пути и номера строк из `.txt` в ответе. Файлы в `/tmp/opencode/books/` считаются временными и не коммитятся.
