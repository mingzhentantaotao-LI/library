#!/usr/bin/env python3
"""Dependency-free web UI and API for the personal knowledge base.

The app stays filesystem-first. A local SQLite database is used only as a
rebuildable index for metadata, summaries, and dashboard statistics.
"""

from __future__ import annotations

import datetime as dt
import contextlib
import json
import mimetypes
import os
import posixpath
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import default as email_policy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


REPO_ROOT = Path(os.environ.get("KB_ROOT", Path(__file__).resolve().parents[1])).resolve()
STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_DB_PATH = Path(
    os.environ.get("KB_INDEX_DB", str(REPO_ROOT / ".cache" / "kb_index.sqlite3"))
).resolve()
INDEX_SYNC_INTERVAL_SECONDS = float(os.environ.get("KB_INDEX_SYNC_INTERVAL_SECONDS", "5"))
MAX_UPLOAD_BYTES = int(os.environ.get("KB_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
MAX_PREVIEW_BYTES = int(os.environ.get("KB_MAX_PREVIEW_BYTES", str(300 * 1024)))
MAX_SEARCH_BYTES = int(os.environ.get("KB_MAX_SEARCH_BYTES", str(800 * 1024)))
MAX_INDEX_TEXT_BYTES = int(os.environ.get("KB_MAX_INDEX_TEXT_BYTES", str(64 * 1024)))
AI_COMMAND = os.environ.get("KB_AI_COMMAND", "").strip()
AI_TIMEOUT_SECONDS = float(os.environ.get("KB_AI_TIMEOUT_SECONDS", "20"))

TEXT_EXTENSIONS = {
    ".css",
    ".csv",
    ".htm",
    ".html",
    ".json",
    ".log",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
SEARCH_ROOTS = ("raw", "wiki")
UPLOAD_TARGETS = ("raw/inbox", "raw/work", "raw/study", "raw/clips", "raw/assets")
DELETE_ROOTS = UPLOAD_TARGETS + (
    "wiki/sources",
    "wiki/projects",
    "wiki/topics",
    "wiki/concepts",
    "wiki/methods",
    "wiki/decisions",
    "wiki/reviews",
)
IGNORED_PARTS = {".git", ".trash", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
INDEX_LOCK = threading.Lock()
INDEX_RUNTIME: dict[str, Any] = {"last_sync_monotonic": 0.0, "last_summary": None}


class ApiError(Exception):
    def __init__(self, status: HTTPStatus, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class FileMeta:
    path: str
    name: str
    section: str
    size: int
    modified: str
    text: bool


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def relative_path(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def safe_repo_path(rel_path: str) -> Path:
    rel_path = urllib.parse.unquote(rel_path or "").replace("\\", "/").strip()
    if not rel_path:
        raise ApiError(HTTPStatus.BAD_REQUEST, "Missing path.")
    normalized = posixpath.normpath(rel_path)
    if normalized.startswith("../") or normalized == ".." or posixpath.isabs(normalized):
        raise ApiError(HTTPStatus.BAD_REQUEST, "Path is outside the knowledge base.")
    path = (REPO_ROOT / normalized).resolve()
    if not is_within(path, REPO_ROOT):
        raise ApiError(HTTPStatus.BAD_REQUEST, "Path is outside the knowledge base.")
    return path


def assert_under_any(path: Path, roots: tuple[str, ...], action: str) -> None:
    allowed = [(REPO_ROOT / root).resolve() for root in roots]
    if not any(is_within(path.resolve(), root) for root in allowed):
        raise ApiError(HTTPStatus.FORBIDDEN, f"Path is not allowed for {action}.")


def is_ignored(path: Path) -> bool:
    return any(part in IGNORED_PARTS for part in path.parts)


def is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS


def read_limited_bytes(path: Path, limit: int) -> tuple[bytes, bool]:
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    truncated = len(data) > limit
    if truncated:
        data = data[:limit]
    return data, truncated


def read_text(path: Path, limit: int = MAX_PREVIEW_BYTES) -> tuple[str, bool]:
    if not is_text_file(path):
        raise ApiError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Only text-like files can be previewed.")
    data, truncated = read_limited_bytes(path, limit)
    return data.decode("utf-8", errors="replace"), truncated


def file_meta(path: Path) -> FileMeta:
    rel = relative_path(path)
    stat = path.stat()
    section = rel.split("/", 1)[0]
    modified = dt.datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
    return FileMeta(
        path=rel,
        name=path.name,
        section=section,
        size=stat.st_size,
        modified=modified,
        text=is_text_file(path),
    )


def scope_roots(scope: str) -> tuple[str, ...]:
    if scope == "raw":
        return ("raw",)
    if scope == "wiki":
        return ("wiki",)
    if scope == "inbox":
        return ("raw/inbox",)
    return SEARCH_ROOTS


def iter_files(scope: str = "all") -> list[Path]:
    files: list[Path] = []
    for root_name in scope_roots(scope):
        root = (REPO_ROOT / root_name).resolve()
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and not is_ignored(path):
                files.append(path)
    return sorted(files, key=lambda p: relative_path(p).lower())


def find_matches(path: Path, query: str, max_lines: int = 3) -> list[dict[str, Any]]:
    if not query or not is_text_file(path) or path.stat().st_size > MAX_SEARCH_BYTES:
        return []
    needle = query.casefold()
    data, _ = read_limited_bytes(path, MAX_SEARCH_BYTES)
    text = data.decode("utf-8", errors="replace")
    matches = []
    for line_no, line in enumerate(text.splitlines(), 1):
        if needle in line.casefold():
            snippet = line.strip()
            if len(snippet) > 220:
                snippet = snippet[:217] + "..."
            matches.append({"line": line_no, "snippet": snippet})
            if len(matches) >= max_lines:
                break
    return matches


def sanitize_filename(name: str) -> str:
    name = Path(name.replace("\\", "/")).name.strip()
    cleaned = "".join(ch if (ch.isalnum() or ch in "._- ") else "-" for ch in name)
    cleaned = re.sub(r"\s+", "-", cleaned).strip(".- ")
    if not cleaned:
        cleaned = f"upload-{int(time.time())}.bin"
    return cleaned[:160]


def unique_destination(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    for index in range(1, 1000):
        next_candidate = directory / f"{stem}-{index}{suffix}"
        if not next_candidate.exists():
            return next_candidate
    raise ApiError(HTTPStatus.CONFLICT, "Could not create a unique filename.")


def parse_multipart(headers: Any, body: bytes) -> tuple[dict[str, str], list[tuple[str, str, bytes]]]:
    content_type = headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        raise ApiError(HTTPStatus.BAD_REQUEST, "Expected multipart/form-data.")
    envelope = (
        f"Content-Type: {content_type}\r\n"
        "MIME-Version: 1.0\r\n\r\n"
    ).encode("utf-8") + body
    message = BytesParser(policy=email_policy).parsebytes(envelope)
    if not message.is_multipart():
        raise ApiError(HTTPStatus.BAD_REQUEST, "Malformed multipart body.")

    fields: dict[str, str] = {}
    files: list[tuple[str, str, bytes]] = []
    for part in message.iter_parts():
        if not part.get("Content-Disposition", ""):
            continue
        name = part.get_param("name", header="content-disposition") or ""
        filename = part.get_filename() or ""
        payload = part.get_payload(decode=True) or b""
        if filename:
            files.append((name, filename, payload))
        elif name:
            fields[name] = payload.decode("utf-8", errors="replace")
    return fields, files


def save_upload(headers: Any, body: bytes) -> list[dict[str, Any]]:
    fields, files = parse_multipart(headers, body)
    target_dir = fields.get("target_dir", "raw/inbox").strip().replace("\\", "/")
    if target_dir not in UPLOAD_TARGETS:
        raise ApiError(HTTPStatus.BAD_REQUEST, "Upload target is not allowed.")
    destination_dir = safe_repo_path(target_dir)
    assert_under_any(destination_dir, UPLOAD_TARGETS, "upload")
    destination_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for _, original_name, payload in files:
        if not payload:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Uploaded file is empty.")
        filename = sanitize_filename(original_name)
        destination = unique_destination(destination_dir, filename)
        destination.write_bytes(payload)
        saved.append(file_meta(destination).__dict__)
    if not saved:
        raise ApiError(HTTPStatus.BAD_REQUEST, "No file found in upload.")
    return saved


def safe_delete(rel_path: str) -> dict[str, str]:
    path = safe_repo_path(rel_path)
    if not path.exists() or not path.is_file():
        raise ApiError(HTTPStatus.NOT_FOUND, "File does not exist.")
    assert_under_any(path, DELETE_ROOTS, "delete")
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    trash_path = REPO_ROOT / ".trash" / timestamp / relative_path(path)
    trash_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(trash_path))
    return {"deleted_path": rel_path, "trash_path": relative_path(trash_path)}


def classify_material(path: str, text: str) -> str:
    blob = f"{path}\n{text[:4000]}".casefold()
    if any(token in blob for token in ("复盘", "项目", "需求", "方案", "weekly", "review", "work")):
        return "work"
    if any(token in blob for token in ("学习", "课程", "笔记", "study", "notes")):
        return "study"
    if any(token in blob for token in ("收藏", "摘录", "bookmark", "clip", "article")):
        return "clip"
    return "inbox"


def extract_title(path: str, text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()[:120]
    return Path(path).stem[:120]


def summarize_locally(text: str) -> str:
    lines = [line.strip(" -\t") for line in text.splitlines() if line.strip()]
    if not lines:
        return "这份材料暂无可预览文本，需要先人工确认文件内容。"
    summary = " ".join(lines[:3])
    if len(summary) > 220:
        summary = summary[:217] + "..."
    return summary


def infer_wiki_targets(path: str, text: str) -> list[str]:
    blob = f"{path}\n{text[:4000]}".casefold()
    targets: list[str] = []
    if "personal-knowledge-base" in blob or "知识库" in blob:
        targets.append("wiki/projects/personal-knowledge-base-v1.md")
        targets.append("wiki/topics/personal-knowledge-base-maintenance.md")
    if any(token in blob for token in ("llm", "agent", "mcp", "codex", "上下文", "ai")):
        targets.append("wiki/topics/llm-context-engineering.md")
    if any(token in blob for token in ("ingest", "上传", "删除", "查询", "流程", "模板")):
        targets.append("wiki/methods/inbox-to-wiki-ingest.md")
    return list(dict.fromkeys(targets))[:5]


def source_page_name(path: str) -> str:
    return f"wiki/sources/{Path(path).stem}.md"


def build_source_draft(path: str, text: str, material_type: str, title: str, summary: str) -> str:
    date = dt.date.today().isoformat()
    return "\n".join(
        [
            f"# 来源：{title}",
            "",
            "## 基本信息",
            "",
            f"- 标题：{title}",
            f"- 来源类型：{material_type}",
            f"- 日期：{date}（记录日期）",
            f"- 原始路径：`{path}`",
            "",
            "## 简要摘要",
            "",
            summary,
            "",
            "## 关键点",
            "",
            "- 需要结合原文进一步确认关键结论。",
            "- 需要判断是否只保留来源登记，还是提升到项目页或主题页。",
            "- 需要在完成整理后补充实际关联页面。",
            "",
            "## 关联页面",
            "",
            "- 暂待整理",
            "",
        ]
    )


def local_ai_suggestion(path: str, text: str) -> dict[str, Any]:
    material_type = classify_material(path, text)
    title = extract_title(path, text)
    summary = summarize_locally(text)
    suggested_archive = {
        "work": "raw/work",
        "study": "raw/study",
        "clip": "raw/clips",
        "inbox": "raw/inbox",
    }[material_type]
    targets = infer_wiki_targets(path, text)
    return {
        "provider": "local-rules",
        "title": title,
        "material_type": material_type,
        "suggested_archive": suggested_archive,
        "source_page": source_page_name(path),
        "wiki_targets": targets,
        "summary": summary,
        "actions": [
            "先保留原件不改写。",
            "如确认值得沉淀，创建同名 wiki/sources 来源页。",
            "如果内容已经形成稳定判断，再更新 1 个项目页和 1 个主题或方法页。",
        ],
        "source_draft": build_source_draft(path, text, material_type, title, summary),
    }


def external_ai_suggestion(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not AI_COMMAND:
        return None
    completed = subprocess.run(
        shlex.split(AI_COMMAND),
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=AI_TIMEOUT_SECONDS,
        check=False,
    )
    if completed.returncode != 0:
        raise ApiError(
            HTTPStatus.BAD_GATEWAY,
            "AI command failed: " + completed.stderr.decode("utf-8", errors="replace")[:500],
        )
    output = completed.stdout.decode("utf-8", errors="replace").strip()
    try:
        result = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ApiError(HTTPStatus.BAD_GATEWAY, f"AI command did not return JSON: {exc}") from exc
    if isinstance(result, dict):
        result.setdefault("provider", "external-command")
        return result
    raise ApiError(HTTPStatus.BAD_GATEWAY, "AI command JSON must be an object.")


def suggest_for_payload(payload: dict[str, Any]) -> dict[str, Any]:
    path = str(payload.get("path", "")).strip()
    text = str(payload.get("text", ""))
    if path and not text:
        file_path = safe_repo_path(path)
        assert_under_any(file_path, SEARCH_ROOTS, "AI suggestion")
        if file_path.exists() and file_path.is_file() and is_text_file(file_path):
            text, _ = read_text(file_path, MAX_SEARCH_BYTES)
    external_payload = {"path": path, "text": text[:MAX_SEARCH_BYTES]}
    external = external_ai_suggestion(external_payload)
    if external:
        return external
    return local_ai_suggestion(path or "unsaved-input.md", text)


def derive_area(rel_path: str) -> str:
    parts = [part for part in rel_path.split("/") if part]
    if len(parts) >= 2 and parts[0] in {"raw", "wiki"}:
        return "/".join(parts[:2])
    return parts[0] if parts else ""


def connect_index_db() -> sqlite3.Connection:
    INDEX_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(INDEX_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


@contextlib.contextmanager
def open_index_db() -> Any:
    conn = connect_index_db()
    try:
        yield conn
    finally:
        conn.close()


def ensure_index_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS files (
            path TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            section TEXT NOT NULL,
            area TEXT NOT NULL,
            suffix TEXT NOT NULL,
            size INTEGER NOT NULL,
            modified TEXT NOT NULL,
            modified_ts REAL NOT NULL,
            text INTEGER NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            preview_text TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_files_section ON files(section);
        CREATE INDEX IF NOT EXISTS idx_files_area ON files(area);
        CREATE INDEX IF NOT EXISTS idx_files_modified_ts ON files(modified_ts DESC);
        CREATE INDEX IF NOT EXISTS idx_files_suffix ON files(suffix);
        """
    )


def set_index_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def get_index_meta(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row else default


def build_index_record(path: Path) -> dict[str, Any]:
    rel = relative_path(path)
    stat = path.stat()
    preview_text = ""
    title = path.stem[:120]
    summary = "非文本文件，已纳入索引但不提供正文预览。"
    if is_text_file(path):
        data, _ = read_limited_bytes(path, MAX_INDEX_TEXT_BYTES)
        preview_text = data.decode("utf-8", errors="replace")
        title = extract_title(rel, preview_text)
        summary = summarize_locally(preview_text)
    return {
        "path": rel,
        "name": path.name,
        "section": rel.split("/", 1)[0],
        "area": derive_area(rel),
        "suffix": path.suffix.lower(),
        "size": stat.st_size,
        "modified": dt.datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "modified_ts": stat.st_mtime,
        "text": 1 if is_text_file(path) else 0,
        "title": title,
        "summary": summary,
        "preview_text": preview_text,
    }


def read_index_status_from_conn(conn: sqlite3.Connection) -> dict[str, Any]:
    ensure_index_schema(conn)
    totals = conn.execute(
        """
        SELECT
            COUNT(*) AS indexed_files,
            COALESCE(SUM(size), 0) AS total_bytes,
            COALESCE(SUM(text), 0) AS text_files
        FROM files
        """
    ).fetchone()
    return {
        "exists": INDEX_DB_PATH.exists(),
        "db_path": str(INDEX_DB_PATH),
        "indexed_files": int(totals["indexed_files"]),
        "text_files": int(totals["text_files"]),
        "total_bytes": int(totals["total_bytes"]),
        "last_indexed_at": get_index_meta(conn, "last_indexed_at") or None,
        "last_rebuild_at": get_index_meta(conn, "last_rebuild_at") or None,
        "last_sync_summary": INDEX_RUNTIME.get("last_summary"),
    }


def sync_index_unlocked(force: bool = False, rebuild: bool = False) -> dict[str, Any]:
    started_at = time.perf_counter()
    current_files = iter_files("all")
    current_map = {relative_path(path): path for path in current_files}
    with open_index_db() as conn:
        ensure_index_schema(conn)
        existing_rows = {
            row["path"]: row
            for row in conn.execute("SELECT path, size, modified_ts FROM files")
        }
        deleted_paths = sorted(set(existing_rows) - set(current_map))
        for rel_path in deleted_paths:
            conn.execute("DELETE FROM files WHERE path = ?", (rel_path,))

        inserted = 0
        updated = 0
        unchanged = 0
        for rel_path, path in current_map.items():
            stat = path.stat()
            row = existing_rows.get(rel_path)
            if (
                row
                and not force
                and int(row["size"]) == stat.st_size
                and abs(float(row["modified_ts"]) - stat.st_mtime) < 1e-6
            ):
                unchanged += 1
                continue
            conn.execute(
                """
                INSERT INTO files (
                    path, name, section, area, suffix, size, modified,
                    modified_ts, text, title, summary, preview_text
                ) VALUES (
                    :path, :name, :section, :area, :suffix, :size, :modified,
                    :modified_ts, :text, :title, :summary, :preview_text
                )
                ON CONFLICT(path) DO UPDATE SET
                    name = excluded.name,
                    section = excluded.section,
                    area = excluded.area,
                    suffix = excluded.suffix,
                    size = excluded.size,
                    modified = excluded.modified,
                    modified_ts = excluded.modified_ts,
                    text = excluded.text,
                    title = excluded.title,
                    summary = excluded.summary,
                    preview_text = excluded.preview_text
                """,
                build_index_record(path),
            )
            if row:
                updated += 1
            else:
                inserted += 1

        finished_at = dt.datetime.now().isoformat(timespec="seconds")
        set_index_meta(conn, "last_indexed_at", finished_at)
        if rebuild:
            set_index_meta(conn, "last_rebuild_at", finished_at)
        conn.commit()

        summary = {
            "scanned": len(current_map),
            "inserted": inserted,
            "updated": updated,
            "deleted": len(deleted_paths),
            "unchanged": unchanged,
            "duration_ms": int((time.perf_counter() - started_at) * 1000),
            "finished_at": finished_at,
            "rebuild": rebuild,
        }
        INDEX_RUNTIME["last_summary"] = summary
        INDEX_RUNTIME["last_sync_monotonic"] = time.monotonic()
        return summary


def maybe_sync_index(force: bool = False) -> dict[str, Any]:
    with INDEX_LOCK:
        now = time.monotonic()
        needs_sync = (
            force
            or not INDEX_DB_PATH.exists()
            or now - float(INDEX_RUNTIME.get("last_sync_monotonic", 0.0)) >= INDEX_SYNC_INTERVAL_SECONDS
        )
        if needs_sync:
            return sync_index_unlocked(force=force, rebuild=False)
        return INDEX_RUNTIME.get("last_summary") or {
            "scanned": 0,
            "inserted": 0,
            "updated": 0,
            "deleted": 0,
            "unchanged": 0,
            "duration_ms": 0,
            "finished_at": None,
            "rebuild": False,
        }


def rebuild_index() -> dict[str, Any]:
    with INDEX_LOCK:
        with open_index_db() as conn:
            ensure_index_schema(conn)
            conn.execute("DELETE FROM files")
            conn.execute("DELETE FROM meta")
            conn.commit()
        return sync_index_unlocked(force=True, rebuild=True)


def get_index_status() -> dict[str, Any]:
    maybe_sync_index()
    with open_index_db() as conn:
        return read_index_status_from_conn(conn)


def indexed_row_to_item(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "path": row["path"],
        "name": row["name"],
        "section": row["section"],
        "area": row["area"],
        "size": int(row["size"]),
        "modified": row["modified"],
        "text": bool(row["text"]),
        "title": row["title"],
        "summary": row["summary"],
        "matches": [],
    }


def index_scope_sql(scope: str) -> tuple[str, tuple[Any, ...]]:
    if scope == "raw":
        return "section = ?", ("raw",)
    if scope == "wiki":
        return "section = ?", ("wiki",)
    if scope == "inbox":
        return "area = ?", ("raw/inbox",)
    return "1 = 1", ()


def list_files_from_filesystem(scope: str = "all", query: str = "") -> list[dict[str, Any]]:
    query = query.strip()
    results = []
    for path in iter_files(scope):
        rel = relative_path(path)
        matches = find_matches(path, query) if query else []
        if query and query.casefold() not in rel.casefold() and not matches:
            continue
        item = file_meta(path).__dict__
        item["matches"] = matches
        item["area"] = derive_area(rel)
        item["title"] = extract_title(rel, matches[0]["snippet"] if matches else "")
        item["summary"] = ""
        results.append(item)
    return results


def indexed_metadata_map(scope: str = "all") -> dict[str, dict[str, Any]]:
    scope_sql, params = index_scope_sql(scope)
    with open_index_db() as conn:
        ensure_index_schema(conn)
        rows = conn.execute(
            f"""
            SELECT path, title, summary, area
            FROM files
            WHERE {scope_sql}
            """,
            params,
        ).fetchall()
    return {
        row["path"]: {
            "title": row["title"],
            "summary": row["summary"],
            "area": row["area"],
        }
        for row in rows
    }


def list_files(scope: str = "all", query: str = "") -> list[dict[str, Any]]:
    query = query.strip()
    try:
        maybe_sync_index()
        if query:
            metadata_map = indexed_metadata_map(scope)
            results = []
            for path in iter_files(scope):
                rel = relative_path(path)
                matches = find_matches(path, query)
                indexed = metadata_map.get(rel, {})
                indexed_hit = any(
                    query.casefold() in str(indexed.get(key, "")).casefold()
                    for key in ("title", "summary", "area")
                )
                if query.casefold() not in rel.casefold() and not matches and not indexed_hit:
                    continue
                item = file_meta(path).__dict__
                item["matches"] = matches
                item["area"] = indexed.get("area", derive_area(rel))
                item["title"] = indexed.get("title", extract_title(rel, ""))
                item["summary"] = indexed.get("summary", "")
                results.append(item)
            return results

        scope_sql, params = index_scope_sql(scope)
        with open_index_db() as conn:
            ensure_index_schema(conn)
            rows = conn.execute(
                f"""
                SELECT path, name, section, area, size, modified, text, title, summary
                FROM files
                WHERE {scope_sql}
                ORDER BY path COLLATE NOCASE
                """,
                params,
            ).fetchall()
        return [indexed_row_to_item(row) for row in rows]
    except sqlite3.Error:
        return list_files_from_filesystem(scope, query)


def dashboard_data_from_filesystem() -> dict[str, Any]:
    files = [file_meta(path) for path in iter_files("all")]
    total_bytes = sum(item.size for item in files)
    summary = {
        "total_files": len(files),
        "text_files": sum(1 for item in files if item.text),
        "raw_files": sum(1 for item in files if item.section == "raw"),
        "wiki_files": sum(1 for item in files if item.section == "wiki"),
        "total_bytes": total_bytes,
    }
    area_map: dict[str, dict[str, Any]] = {}
    suffix_map: dict[str, int] = {}
    recent_rows = []
    for path in iter_files("all"):
        rel = relative_path(path)
        meta = file_meta(path)
        area = derive_area(rel)
        entry = area_map.setdefault(area, {"name": area, "files": 0, "bytes": 0})
        entry["files"] += 1
        entry["bytes"] += meta.size
        suffix = path.suffix.lower() or "[none]"
        suffix_map[suffix] = suffix_map.get(suffix, 0) + 1
        recent_rows.append(
            {
                "path": rel,
                "title": path.stem,
                "summary": "",
                "modified": meta.modified,
                "size": meta.size,
                "section": meta.section,
            }
        )
    recent_rows.sort(key=lambda item: item["modified"], reverse=True)
    areas = sorted(area_map.values(), key=lambda item: (-item["files"], item["name"]))[:8]
    suffixes = [
        {"suffix": suffix, "files": count}
        for suffix, count in sorted(suffix_map.items(), key=lambda item: (-item[1], item[0]))[:8]
    ]
    return {
        "summary": summary,
        "areas": areas,
        "suffixes": suffixes,
        "recent_files": recent_rows[:8],
        "index_status": {
            "exists": False,
            "db_path": str(INDEX_DB_PATH),
            "indexed_files": 0,
            "text_files": 0,
            "total_bytes": 0,
            "last_indexed_at": None,
            "last_rebuild_at": None,
            "last_sync_summary": None,
        },
    }


def dashboard_data() -> dict[str, Any]:
    try:
        maybe_sync_index()
        with open_index_db() as conn:
            ensure_index_schema(conn)
            summary_row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_files,
                    COALESCE(SUM(text), 0) AS text_files,
                    COALESCE(SUM(CASE WHEN section = 'raw' THEN 1 ELSE 0 END), 0) AS raw_files,
                    COALESCE(SUM(CASE WHEN section = 'wiki' THEN 1 ELSE 0 END), 0) AS wiki_files,
                    COALESCE(SUM(size), 0) AS total_bytes
                FROM files
                """
            ).fetchone()
            areas = [
                {"name": row["area"], "files": int(row["files"]), "bytes": int(row["bytes"])}
                for row in conn.execute(
                    """
                    SELECT area, COUNT(*) AS files, COALESCE(SUM(size), 0) AS bytes
                    FROM files
                    GROUP BY area
                    ORDER BY files DESC, area ASC
                    LIMIT 8
                    """
                ).fetchall()
            ]
            suffixes = [
                {
                    "suffix": row["suffix"] or "[none]",
                    "files": int(row["files"]),
                }
                for row in conn.execute(
                    """
                    SELECT suffix, COUNT(*) AS files
                    FROM files
                    GROUP BY suffix
                    ORDER BY files DESC, suffix ASC
                    LIMIT 8
                    """
                ).fetchall()
            ]
            recent_files = [
                {
                    "path": row["path"],
                    "title": row["title"],
                    "summary": row["summary"],
                    "modified": row["modified"],
                    "size": int(row["size"]),
                    "section": row["section"],
                }
                for row in conn.execute(
                    """
                    SELECT path, title, summary, modified, size, section
                    FROM files
                    ORDER BY modified_ts DESC, path ASC
                    LIMIT 8
                    """
                ).fetchall()
            ]
            return {
                "summary": {
                    "total_files": int(summary_row["total_files"]),
                    "text_files": int(summary_row["text_files"]),
                    "raw_files": int(summary_row["raw_files"]),
                    "wiki_files": int(summary_row["wiki_files"]),
                    "total_bytes": int(summary_row["total_bytes"]),
                },
                "areas": areas,
                "suffixes": suffixes,
                "recent_files": recent_files,
                "index_status": read_index_status_from_conn(conn),
            }
    except sqlite3.Error:
        return dashboard_data_from_filesystem()


class KnowledgeBaseHandler(BaseHTTPRequestHandler):
    server_version = "PersonalKnowledgeBaseWeb/0.2"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), fmt % args))

    def send_json(self, status: HTTPStatus, payload: dict[str, Any] | list[Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_error_json(self, error: ApiError) -> None:
        self.send_json(error.status, {"error": error.message})

    def send_internal_error(self, error: Exception) -> None:
        self.log_message("Unhandled error: %s", error)
        self.send_error_json(ApiError(HTTPStatus.INTERNAL_SERVER_ERROR, "Internal server error."))

    def read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > MAX_UPLOAD_BYTES:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Request body is too large.")
        return self.rfile.read(length)

    def parsed_query(self) -> tuple[str, dict[str, list[str]]]:
        parsed = urllib.parse.urlparse(self.path)
        return parsed.path, urllib.parse.parse_qs(parsed.query)

    def do_GET(self) -> None:
        try:
            path, query = self.parsed_query()
            if path in ("", "/"):
                self.serve_static("index.html")
            elif path.startswith("/static/"):
                self.serve_static(path.removeprefix("/static/"))
            elif path == "/api/health":
                index_status = get_index_status()
                self.send_json(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "repo_root": str(REPO_ROOT),
                        "ai_provider": "external-command" if AI_COMMAND else "local-rules",
                        "files": int(index_status["indexed_files"]),
                        "index": index_status,
                    },
                )
            elif path == "/api/dashboard":
                self.send_json(HTTPStatus.OK, dashboard_data())
            elif path == "/api/index/status":
                self.send_json(HTTPStatus.OK, get_index_status())
            elif path in ("/api/files", "/api/search"):
                scope = query.get("scope", ["all"])[0]
                q = query.get("q", [""])[0]
                self.send_json(HTTPStatus.OK, {"items": list_files(scope, q)})
            elif path == "/api/file":
                rel = query.get("path", [""])[0]
                file_path = safe_repo_path(rel)
                assert_under_any(file_path, SEARCH_ROOTS, "preview")
                if not file_path.exists() or not file_path.is_file():
                    raise ApiError(HTTPStatus.NOT_FOUND, "File does not exist.")
                text, truncated = read_text(file_path)
                self.send_json(
                    HTTPStatus.OK,
                    {
                        "path": relative_path(file_path),
                        "content": text,
                        "truncated": truncated,
                    },
                )
            else:
                raise ApiError(HTTPStatus.NOT_FOUND, "Not found.")
        except ApiError as error:
            self.send_error_json(error)
        except Exception as error:
            self.send_internal_error(error)

    def do_HEAD(self) -> None:
        try:
            path, _ = self.parsed_query()
            if path in ("", "/"):
                self.serve_static("index.html", head_only=True)
            elif path.startswith("/static/"):
                self.serve_static(path.removeprefix("/static/"), head_only=True)
            elif path.startswith("/api/"):
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                raise ApiError(HTTPStatus.NOT_FOUND, "Not found.")
        except ApiError as error:
            self.send_error_json(error)
        except Exception as error:
            self.send_internal_error(error)

    def do_POST(self) -> None:
        try:
            path, _ = self.parsed_query()
            body = self.read_body()
            if path == "/api/upload":
                items = save_upload(self.headers, body)
                maybe_sync_index(force=True)
                self.send_json(HTTPStatus.CREATED, {"items": items})
            elif path == "/api/ai/suggest":
                payload = json.loads(body.decode("utf-8")) if body else {}
                self.send_json(HTTPStatus.OK, suggest_for_payload(payload))
            elif path == "/api/index/rebuild":
                self.send_json(HTTPStatus.OK, rebuild_index())
            else:
                raise ApiError(HTTPStatus.NOT_FOUND, "Not found.")
        except json.JSONDecodeError:
            self.send_error_json(ApiError(HTTPStatus.BAD_REQUEST, "Malformed JSON body."))
        except ApiError as error:
            self.send_error_json(error)
        except Exception as error:
            self.send_internal_error(error)

    def do_DELETE(self) -> None:
        try:
            path, query = self.parsed_query()
            if path != "/api/file":
                raise ApiError(HTTPStatus.NOT_FOUND, "Not found.")
            rel = query.get("path", [""])[0]
            result = safe_delete(rel)
            maybe_sync_index(force=True)
            self.send_json(HTTPStatus.OK, result)
        except ApiError as error:
            self.send_error_json(error)
        except Exception as error:
            self.send_internal_error(error)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Allow", "GET,HEAD,POST,DELETE,OPTIONS")
        self.end_headers()

    def serve_static(self, rel_path: str, head_only: bool = False) -> None:
        rel_path = rel_path.split("?", 1)[0].strip("/") or "index.html"
        candidate = (STATIC_DIR / rel_path).resolve()
        if not is_within(candidate, STATIC_DIR) or not candidate.exists() or not candidate.is_file():
            raise ApiError(HTTPStatus.NOT_FOUND, "Static file not found.")
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        data = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if not head_only:
            self.wfile.write(data)


def main() -> None:
    host = os.environ.get("KB_HOST", "127.0.0.1")
    port = int(os.environ.get("KB_PORT", "8080"))
    server = ThreadingHTTPServer((host, port), KnowledgeBaseHandler)
    print(f"Personal knowledge base web UI: http://{host}:{port}")
    print(f"Repository root: {REPO_ROOT}")
    print(f"Index database: {INDEX_DB_PATH}")
    print(f"AI provider: {'external-command' if AI_COMMAND else 'local-rules'}")
    server.serve_forever()


if __name__ == "__main__":
    main()
