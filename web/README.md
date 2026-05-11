# Web UI

This is a thin, dependency-free web layer for the personal knowledge base. It keeps the current filesystem model as the source of truth and uses SQLite only as a rebuildable metadata/search index.

## Run

```bash
python3 web/server.py
```

Optional environment variables:

- `KB_HOST`: bind host, defaults to `127.0.0.1`.
- `KB_PORT`: bind port, defaults to `8080`.
- `KB_ROOT`: repository root, defaults to the parent directory of `web/`.
- `KB_AUTH_REQUIRED`: set to `1` to protect APIs with login.
- `KB_AUTH_USERNAME`: login username, defaults to `admin`.
- `KB_AUTH_PASSWORD`: login password. Leave unset only for local development.
- `KB_SESSION_SECRET`: random secret for the server environment.
- `KB_AI_COMMAND`: optional external AI command. The server sends JSON through stdin and expects a JSON object through stdout.
- `KB_AI_API_KEY`: optional OpenAI-compatible API key.
- `KB_AI_ENDPOINT`: optional OpenAI-compatible chat completions endpoint.
- `KB_AI_MODEL`: optional model name, defaults to `gpt-5.5`.

## Current Capabilities

- Query files under `raw/` and `wiki/`.
- Preview text-like files.
- Upload files to `raw/inbox`, `raw/work`, `raw/study`, `raw/clips`, or `raw/assets`.
- Delete by moving files into `.trash/` instead of removing them permanently.
- Generate file-management suggestions through local rules, `KB_AI_COMMAND`, or an OpenAI-compatible HTTP provider when configured.
- Process raw materials by creating `wiki/sources/` drafts, archiving the raw file, and rebuilding the SQLite index.
- Hide non-production sample material under `raw/examples/` and `wiki/examples/`.

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
