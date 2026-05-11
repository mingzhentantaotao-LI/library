# Web UI

This is a thin, dependency-free web layer for the personal knowledge base. It keeps the current filesystem model and does not introduce a database.

## Run

```bash
python3 web/server.py
```

Optional environment variables:

- `KB_HOST`: bind host, defaults to `127.0.0.1`.
- `KB_PORT`: bind port, defaults to `8080`.
- `KB_ROOT`: repository root, defaults to the parent directory of `web/`.
- `KB_AI_COMMAND`: optional external AI command. The server sends JSON through stdin and expects a JSON object through stdout.

## Current Capabilities

- Query files under `raw/` and `wiki/`.
- Preview text-like files.
- Upload files to `raw/inbox`, `raw/work`, `raw/study`, `raw/clips`, or `raw/assets`.
- Delete by moving files into `.trash/` instead of removing them permanently.
- Generate file-management suggestions through local rules, or through `KB_AI_COMMAND` when configured.

## AI Command Contract

The external command receives:

```json
{
  "path": "raw/inbox/example.md",
  "text": "file preview text"
}
```

It should return a JSON object. Useful keys include:

- `title`
- `material_type`
- `suggested_archive`
- `source_page`
- `wiki_targets`
- `summary`
- `actions`
- `source_draft`
