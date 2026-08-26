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

### Search scientific articles

```
GET /api/scimag/search?q={query}&limit=20&offset=0
```

**Parameters:**
- `q` — search query (required)
- `limit` — results per page (default 20)
- `offset` — pagination offset (default 0)

**Note:** All 82M+ articles indexed; there is no file on disk — downloading returns 404.

**Example via curl:**
```bash
curl --fail --location 'http://192.168.0.153:8000/api/scimag/search?q=transformer+attention&limit=5'
```

**Example via webfetch:**
```
http://192.168.0.153:8000/api/scimag/search?q=transformer+attention&limit=5
```

### Download scientific article

```
GET /api/scimag/file/{id}
```

**Parameters:**
- `id` — article ID from scimag search results

Streams the article from the underlying zip archive in 256 KB chunks. Falls back to member matching via `unquote` when direct ID lookup fails.

**Example:**
```bash
curl --fail --location --output '/tmp/opencode/article.pdf' 'http://192.168.0.153:8000/api/scimag/file/12345678'
```

### Extract text from PDF (optional)

```bash
pdftotext '/tmp/opencode/book.pdf' '/tmp/opencode/book.txt'
```

## Typical workflow

**Books:**
1. Search for a book via `/api/search` with the desired query
2. Pick a result, note its `md5`
3. Download the file via `/api/file/{md5}`

**Scientific articles (scimag):**
1. Search for an article via `/api/scimag/search` with the desired query
2. Pick a result, note its `id`
3. Stream the article via `/api/scimag/file/{id}`

## Download policy

Feel free to download books and articles into `/tmp/opencode/` to verify claims against primary sources — this is the standard workflow. Downloads to `/tmp/opencode/` are allowed even in plan mode (read-only for the working directory, but not for temp). After downloading, extract text with `pdftotext` and search it; include file paths and line numbers from the `.txt` in your response when relevant. Files in `/tmp/opencode/` are considered temporary and must not be committed.
