#!/usr/bin/env python3
"""Dependency-free Web UI and API for the personal knowledge base.

The knowledge base remains filesystem-first. SQLite is a rebuildable index for
metadata, search acceleration, dashboard statistics, and pipeline status.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hmac
import json
import mimetypes
import os
import posixpath
import re
import shlex
import shutil
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import default as email_policy
from http import HTTPStatus
from http.cookies import SimpleCookie
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

AUTH_USERNAME = os.environ.get("KB_AUTH_USERNAME", "admin")
AUTH_PASSWORD = os.environ.get("KB_AUTH_PASSWORD", "").strip()
AUTH_REQUIRED = os.environ.get("KB_AUTH_REQUIRED", "1" if AUTH_PASSWORD else "0").lower() not in {
    "0",
    "false",
    "no",
    "off",
}
SESSION_COOKIE_NAME = os.environ.get("KB_SESSION_COOKIE", "kb_session")
SESSION_TTL_SECONDS = int(os.environ.get("KB_SESSION_TTL_SECONDS", str(8 * 60 * 60)))
SESSION_SECRET = os.environ.get("KB_SESSION_SECRET", secrets.token_urlsafe(32))

AI_COMMAND = os.environ.get("KB_AI_COMMAND", "").strip()
AI_TIMEOUT_SECONDS = float(os.environ.get("KB_AI_TIMEOUT_SECONDS", "20"))
AI_HTTP_API_KEY = os.environ.get("KB_AI_API_KEY", os.environ.get("OPENAI_API_KEY", "")).strip()
AI_HTTP_ENDPOINT = os.environ.get(
    "KB_AI_ENDPOINT",
    "https://api.openai.com/v1/chat/completions",
).strip()
AI_HTTP_MODEL = os.environ.get("KB_AI_MODEL", "gpt-5.5").strip()

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
ARCHIVE_TARGETS = ("raw/work", "raw/study", "raw/clips", "raw/assets")
DELETE_ROOTS = UPLOAD_TARGETS + (
    "wiki/sources",
    "wiki/projects",
    "wiki/topics",
    "wiki/concepts",
    "wiki/methods",
    "wiki/decisions",
    "wiki/reviews",
)
SOURCE_ROOTS = ("wiki/sources",)
IGNORED_PARTS = {
    ".git",
    ".trash",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "examples",
}

INDEX_LOCK = threading.Lock()
INDEX_RUNTIME: dict[str, Any] = {"last_sync_monotonic": 0.0, "last_summary": None}
SESSION_LOCK = threading.Lock()
SESSIONS: dict[str, dict[str, Any]] = {}


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
    try:
        parts = path.resolve().relative_to(REPO_ROOT).parts
    except ValueError:
        parts = path.parts
    return any(part in IGNORED_PARTS for part in parts)


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
    return FileMeta(
        path=rel,
        name=path.name,
        section=rel.split("/", 1)[0],
        size=stat.st_size,
        modified=dt.datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
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


def count_example_files() -> int:
    total = 0
    for root_name in ("raw/examples", "wiki/examples"):
        root = REPO_ROOT / root_name
        if root.exists():
            total += sum(1 for path in root.rglob("*") if path.is_file())
    return total


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
    directory.mkdir(parents=True, exist_ok=True)
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
            title = line.lstrip("#").strip()
            if title:
                return title[:120]
    return Path(path).stem[:120]


def summarize_locally(text: str) -> str:
    lines = [line.strip(" -\t") for line in text.splitlines() if line.strip()]
    if not lines:
        return "这份资料暂无可预览文本，需要先人工确认文件内容。"
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
    if any(token in blob for token in ("ingest", "上传", "删除", "查询", "流程", "模板", "pipeline")):
        targets.append("wiki/methods/inbox-to-wiki-ingest.md")
    return list(dict.fromkeys(targets))[:5]


def source_page_name(path: str) -> str:
    return f"wiki/sources/{Path(path).stem}.md"


def markdown_list(items: list[str], fallback: str) -> list[str]:
    if not items:
        return [f"- {fallback}"]
    return [f"- {item}" for item in items]


def build_source_draft(
    path: str,
    text: str,
    material_type: str,
    title: str,
    summary: str,
    wiki_targets: list[str] | None = None,
    actions: list[str] | None = None,
    provider: str = "local-rules",
) -> str:
    date = dt.date.today().isoformat()
    target_lines = markdown_list(wiki_targets or [], "暂不提升到其他页面")
    action_lines = markdown_list(
        actions or [],
        "人工复核摘要与关联页面，再决定是否提升到项目页、主题页或方法页。",
    )
    return "\n".join(
        [
            f"# 来源：{title}",
            "",
            "## 基本信息",
            "",
            f"- 标题：{title}",
            f"- 来源类型：{material_type}",
            f"- 记录日期：{date}",
            f"- 原始路径：`{path}`",
            f"- 处理来源：{provider}",
            "",
            "## 摘要",
            "",
            summary,
            "",
            "## 关键点",
            "",
            "- 需要结合原文进一步确认关键结论。",
            "- 需要判断是只保留来源登记，还是提升到项目页、主题页或方法页。",
            "- 完成整理后补充实际关联页面与回链。",
            "",
            "## 建议关联",
            "",
            *target_lines,
            "",
            "## 下一步",
            "",
            *action_lines,
            "",
        ]
    )


def normalize_ai_suggestion(path: str, text: str, result: dict[str, Any], provider: str) -> dict[str, Any]:
    material_type = str(result.get("material_type") or classify_material(path, text)).strip()
    if material_type not in {"work", "study", "clip", "inbox"}:
        material_type = "inbox"
    title = str(result.get("title") or extract_title(path, text)).strip()[:120]
    summary = str(result.get("summary") or summarize_locally(text)).strip()
    suggested_archive = str(result.get("suggested_archive") or "").strip().replace("\\", "/")
    if suggested_archive not in ("raw/inbox", *ARCHIVE_TARGETS):
        suggested_archive = {
            "work": "raw/work",
            "study": "raw/study",
            "clip": "raw/clips",
            "inbox": "raw/inbox",
        }[material_type]
    wiki_targets = [
        str(target).strip().replace("\\", "/")
        for target in result.get("wiki_targets", infer_wiki_targets(path, text)) or []
        if str(target).strip().replace("\\", "/").startswith("wiki/")
    ][:5]
    actions = [str(action).strip() for action in result.get("actions", []) or [] if str(action).strip()][:5]
    source_page = str(result.get("source_page") or source_page_name(path)).strip().replace("\\", "/")
    try:
        source_path = safe_repo_path(source_page)
        assert_under_any(source_path, SOURCE_ROOTS, "source page")
    except ApiError:
        source_page = source_page_name(path)
    source_draft = str(result.get("source_draft") or "").strip()
    if not source_draft:
        source_draft = build_source_draft(
            path,
            text,
            material_type,
            title,
            summary,
            wiki_targets,
            actions,
            provider,
        )
    return {
        "provider": provider,
        "title": title,
        "material_type": material_type,
        "suggested_archive": suggested_archive,
        "source_page": source_page,
        "wiki_targets": wiki_targets,
        "summary": summary,
        "actions": actions
        or [
            "先保留原件不改写。",
            "确认值得沉淀后创建同名 wiki/sources 来源页。",
            "内容形成稳定判断后，再更新 1 个项目页和 1 个主题/方法页。",
        ],
        "source_draft": source_draft,
    }


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
    return normalize_ai_suggestion(
        path,
        text,
        {
            "title": title,
            "material_type": material_type,
            "suggested_archive": suggested_archive,
            "source_page": source_page_name(path),
            "wiki_targets": targets,
            "summary": summary,
            "actions": [
                "先保留原件不改写。",
                "如确认值得沉淀，创建同名 wiki/sources 来源页。",
                "如内容已经形成稳定判断，再更新 1 个项目页和 1 个主题或方法页。",
            ],
        },
        "local-rules",
    )


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    if not cleaned.startswith("{"):
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]
    result = json.loads(cleaned)
    if not isinstance(result, dict):
        raise ValueError("AI JSON must be an object.")
    return result


def external_command_suggestion(payload: dict[str, Any]) -> dict[str, Any] | None:
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
        result = parse_json_object(output)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ApiError(HTTPStatus.BAD_GATEWAY, f"AI command did not return JSON: {exc}") from exc
    return normalize_ai_suggestion(
        str(payload.get("path", "")),
        str(payload.get("text", "")),
        result,
        "external-command",
    )


def extract_ai_content(response_json: dict[str, Any]) -> str:
    if isinstance(response_json.get("output_text"), str):
        return response_json["output_text"]
    choices = response_json.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(
                str(part.get("text", ""))
                for part in content
                if isinstance(part, dict) and part.get("text")
            )
    output = response_json.get("output")
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            for part in item.get("content", []) or []:
                if isinstance(part, dict) and part.get("text"):
                    chunks.append(str(part["text"]))
        if chunks:
            return "\n".join(chunks)
    return ""


def http_ai_suggestion(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not AI_HTTP_API_KEY:
        return None
    system_prompt = (
        "你是个人知识库资料整理助手。只返回 JSON，不要 Markdown。"
        "字段必须包括 title, material_type, suggested_archive, source_page, "
        "wiki_targets, summary, actions。material_type 只能是 work/study/clip/inbox。"
        "suggested_archive 只能是 raw/work, raw/study, raw/clips, raw/assets, raw/inbox。"
    )
    user_prompt = {
        "path": payload.get("path", ""),
        "text": str(payload.get("text", ""))[:MAX_SEARCH_BYTES],
    }
    request_payload = {
        "model": AI_HTTP_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
        ],
        "temperature": 0.2,
    }
    request = urllib.request.Request(
        AI_HTTP_ENDPOINT,
        data=json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {AI_HTTP_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=AI_TIMEOUT_SECONDS) as response:
            response_data = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise ApiError(HTTPStatus.BAD_GATEWAY, f"AI HTTP request failed ({exc.code}): {body}") from exc
    except urllib.error.URLError as exc:
        raise ApiError(HTTPStatus.BAD_GATEWAY, f"AI HTTP request failed: {exc.reason}") from exc

    try:
        response_json = json.loads(response_data)
        content = extract_ai_content(response_json)
        result = parse_json_object(content)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ApiError(HTTPStatus.BAD_GATEWAY, f"AI HTTP response did not contain valid JSON: {exc}") from exc
    return normalize_ai_suggestion(
        str(payload.get("path", "")),
        str(payload.get("text", "")),
        result,
        "openai-compatible-http",
    )


def active_ai_provider() -> str:
    if AI_COMMAND:
        return "external-command"
    if AI_HTTP_API_KEY:
        return "openai-compatible-http"
    return "local-rules"


def suggest_for_payload(payload: dict[str, Any]) -> dict[str, Any]:
    path = str(payload.get("path", "")).strip()
    text = str(payload.get("text", ""))
    if path and not text:
        file_path = safe_repo_path(path)
        assert_under_any(file_path, SEARCH_ROOTS, "AI suggestion")
        if file_path.exists() and file_path.is_file() and is_text_file(file_path):
            text, _ = read_text(file_path, MAX_SEARCH_BYTES)
    external_payload = {"path": path, "text": text[:MAX_SEARCH_BYTES]}
    command_result = external_command_suggestion(external_payload)
    if command_result:
        return command_result
    http_result = http_ai_suggestion(external_payload)
    if http_result:
        return http_result
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
            COALESCE(SUM(text), 0) AS text_files,
            COALESCE(SUM(size), 0) AS total_bytes
        FROM files
        """
    ).fetchone()
    return {
        "exists": INDEX_DB_PATH.exists(),
        "db_path": str(INDEX_DB_PATH),
        "indexed_files": int(totals["indexed_files"]),
        "text_files": int(totals["text_files"]),
        "total_bytes": int(totals["total_bytes"]),
        "last_indexed_at": get_index_meta(conn, "last_indexed_at", None),
        "last_rebuild_at": get_index_meta(conn, "last_rebuild_at", None),
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
    return {
        "summary": {
            "total_files": len(files),
            "text_files": sum(1 for item in files if item.text),
            "raw_files": sum(1 for item in files if item.section == "raw"),
            "wiki_files": sum(1 for item in files if item.section == "wiki"),
            "total_bytes": total_bytes,
        },
        "areas": sorted(area_map.values(), key=lambda item: (-item["files"], item["name"]))[:8],
        "suffixes": [
            {"suffix": suffix, "files": count}
            for suffix, count in sorted(suffix_map.items(), key=lambda item: (-item[1], item[0]))[:8]
        ],
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
                {"suffix": row["suffix"] or "[none]", "files": int(row["files"])}
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


def pipeline_status() -> dict[str, Any]:
    maybe_sync_index()
    inbox_items = list_files("inbox")
    raw_files = iter_files("raw")
    gaps = []
    for path in raw_files:
        rel = relative_path(path)
        source_rel = source_page_name(rel)
        if not (REPO_ROOT / source_rel).exists():
            meta = file_meta(path).__dict__
            meta["source_page"] = source_rel
            meta["area"] = derive_area(rel)
            gaps.append(meta)
    return {
        "inbox_count": len(inbox_items),
        "source_gaps_count": len(gaps),
        "source_gaps": gaps[:20],
        "examples_hidden": count_example_files(),
        "upload_targets": list(UPLOAD_TARGETS),
        "archive_targets": list(ARCHIVE_TARGETS),
        "ai_provider": active_ai_provider(),
        "auth_required": AUTH_REQUIRED,
    }


def process_material(
    rel_path: str,
    create_source: bool = True,
    archive: bool = True,
    overwrite_source: bool = False,
) -> dict[str, Any]:
    path = safe_repo_path(rel_path)
    if not path.exists() or not path.is_file():
        raise ApiError(HTTPStatus.NOT_FOUND, "File does not exist.")
    assert_under_any(path, UPLOAD_TARGETS, "process")
    if is_ignored(path):
        raise ApiError(HTTPStatus.FORBIDDEN, "Ignored/example files are not processed.")

    original_rel = relative_path(path)
    text = ""
    if is_text_file(path):
        text, _ = read_text(path, MAX_SEARCH_BYTES)
    suggestion = suggest_for_payload({"path": original_rel, "text": text})

    actions: list[dict[str, Any]] = []
    final_path = path
    final_rel = original_rel
    target_dir = str(suggestion.get("suggested_archive") or "raw/inbox").replace("\\", "/")
    if target_dir not in ("raw/inbox", *ARCHIVE_TARGETS):
        target_dir = "raw/inbox"
    if archive and target_dir in ARCHIVE_TARGETS:
        target_root = safe_repo_path(target_dir)
        assert_under_any(target_root, ARCHIVE_TARGETS, "archive")
        if not is_within(path, target_root):
            final_path = unique_destination(target_root, path.name)
            shutil.move(str(path), str(final_path))
            final_rel = relative_path(final_path)
            actions.append({"type": "archive", "from": original_rel, "to": final_rel})
        else:
            actions.append({"type": "archive_skipped", "reason": "already_in_target", "path": final_rel})
    elif archive:
        actions.append({"type": "archive_skipped", "reason": "kept_in_inbox", "path": final_rel})

    source_rel = str(suggestion.get("source_page") or source_page_name(original_rel)).replace("\\", "/")
    try:
        source_path = safe_repo_path(source_rel)
        assert_under_any(source_path, SOURCE_ROOTS, "create source")
    except ApiError:
        source_rel = source_page_name(original_rel)
        source_path = safe_repo_path(source_rel)
    if create_source:
        if source_path.exists() and not overwrite_source:
            actions.append({"type": "source_exists", "path": source_rel})
        else:
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_text = build_source_draft(
                final_rel,
                text,
                str(suggestion.get("material_type") or "inbox"),
                str(suggestion.get("title") or extract_title(final_rel, text)),
                str(suggestion.get("summary") or summarize_locally(text)),
                list(suggestion.get("wiki_targets") or []),
                list(suggestion.get("actions") or []),
                str(suggestion.get("provider") or active_ai_provider()),
            )
            source_path.write_text(source_text, encoding="utf-8")
            actions.append({"type": "source_created", "path": source_rel})
    else:
        actions.append({"type": "source_skipped", "path": source_rel})

    index_summary = maybe_sync_index(force=True)
    return {
        "path": original_rel,
        "final_path": final_rel,
        "source_page": source_rel,
        "suggestion": suggestion,
        "actions": actions,
        "index": index_summary,
    }


def prune_sessions_unlocked(now: float | None = None) -> None:
    now = time.time() if now is None else now
    expired = [token for token, item in SESSIONS.items() if float(item["expires_at"]) <= now]
    for token in expired:
        SESSIONS.pop(token, None)


def create_session(username: str) -> str:
    token = secrets.token_urlsafe(32)
    with SESSION_LOCK:
        prune_sessions_unlocked()
        SESSIONS[token] = {
            "username": username,
            "created_at": time.time(),
            "expires_at": time.time() + SESSION_TTL_SECONDS,
        }
    return token


def session_for_token(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    with SESSION_LOCK:
        prune_sessions_unlocked()
        session = SESSIONS.get(token)
        if not session:
            return None
        session["expires_at"] = time.time() + SESSION_TTL_SECONDS
        return dict(session)


def drop_session(token: str) -> None:
    with SESSION_LOCK:
        SESSIONS.pop(token, None)


def auth_status(authenticated: bool, username: str | None = None) -> dict[str, Any]:
    return {
        "required": AUTH_REQUIRED,
        "configured": bool(AUTH_PASSWORD) or not AUTH_REQUIRED,
        "authenticated": authenticated or not AUTH_REQUIRED,
        "username": username if authenticated else (AUTH_USERNAME if not AUTH_REQUIRED else None),
        "session_ttl_seconds": SESSION_TTL_SECONDS,
    }


class KnowledgeBaseHandler(BaseHTTPRequestHandler):
    server_version = "PersonalKnowledgeBaseWeb/0.3"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), fmt % args))

    def send_json(
        self,
        status: HTTPStatus,
        payload: dict[str, Any] | list[Any],
        *,
        no_store: bool = False,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if no_store:
            self.send_header("Cache-Control", "no-store")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def send_error_json(self, error: ApiError) -> None:
        self.send_json(error.status, {"error": error.message}, no_store=error.status == HTTPStatus.UNAUTHORIZED)

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

    def cookie_token(self) -> str:
        cookie_header = self.headers.get("Cookie", "")
        if not cookie_header:
            return ""
        cookie = SimpleCookie()
        cookie.load(cookie_header)
        morsel = cookie.get(SESSION_COOKIE_NAME)
        return morsel.value if morsel else ""

    def current_session(self) -> dict[str, Any] | None:
        return session_for_token(self.cookie_token())

    def is_https_request(self) -> bool:
        proto = self.headers.get("X-Forwarded-Proto", "").split(",", 1)[0].strip().lower()
        return proto == "https"

    def session_cookie(self, token: str, max_age: int = SESSION_TTL_SECONDS) -> str:
        cookie = SimpleCookie()
        cookie[SESSION_COOKIE_NAME] = token
        cookie[SESSION_COOKIE_NAME]["path"] = "/"
        cookie[SESSION_COOKIE_NAME]["max-age"] = str(max_age)
        cookie[SESSION_COOKIE_NAME]["httponly"] = True
        cookie[SESSION_COOKIE_NAME]["samesite"] = "Lax"
        if self.is_https_request():
            cookie[SESSION_COOKIE_NAME]["secure"] = True
        return cookie.output(header="").strip()

    def clear_session_cookie(self) -> str:
        parts = [f"{SESSION_COOKIE_NAME}=", "Path=/", "Max-Age=0", "HttpOnly", "SameSite=Lax"]
        if self.is_https_request():
            parts.append("Secure")
        return "; ".join(parts)

    def is_public_api(self, path: str, method: str) -> bool:
        return (method == "GET" and path == "/api/auth/status") or (
            method == "POST" and path in {"/api/auth/login", "/api/auth/logout"}
        )

    def require_auth(self, path: str, method: str) -> dict[str, Any] | None:
        if not path.startswith("/api/") or self.is_public_api(path, method) or not AUTH_REQUIRED:
            return self.current_session()
        session = self.current_session()
        if not session:
            raise ApiError(HTTPStatus.UNAUTHORIZED, "Login required.")
        return session

    def do_GET(self) -> None:
        try:
            path, query = self.parsed_query()
            self.require_auth(path, "GET")
            if path in ("", "/"):
                self.serve_static("index.html")
            elif path.startswith("/static/"):
                self.serve_static(path.removeprefix("/static/"))
            elif path == "/api/auth/status":
                session = self.current_session()
                self.send_json(
                    HTTPStatus.OK,
                    auth_status(bool(session), session.get("username") if session else None),
                    no_store=True,
                )
            elif path == "/api/health":
                index_status = get_index_status()
                self.send_json(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "repo_root": str(REPO_ROOT),
                        "ai_provider": active_ai_provider(),
                        "ai_model": AI_HTTP_MODEL if AI_HTTP_API_KEY else None,
                        "ai_endpoint": AI_HTTP_ENDPOINT if AI_HTTP_API_KEY else None,
                        "auth_required": AUTH_REQUIRED,
                        "files": int(index_status["indexed_files"]),
                        "index": index_status,
                    },
                )
            elif path == "/api/dashboard":
                self.send_json(HTTPStatus.OK, dashboard_data())
            elif path == "/api/index/status":
                self.send_json(HTTPStatus.OK, get_index_status())
            elif path == "/api/pipeline/status":
                self.send_json(HTTPStatus.OK, pipeline_status())
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
            self.require_auth(path, "HEAD")
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
            self.require_auth(path, "POST")
            body = self.read_body()
            if path == "/api/auth/login":
                payload = json.loads(body.decode("utf-8")) if body else {}
                if AUTH_REQUIRED and not AUTH_PASSWORD:
                    raise ApiError(HTTPStatus.SERVICE_UNAVAILABLE, "Authentication is required but not configured.")
                username = str(payload.get("username", ""))
                password = str(payload.get("password", ""))
                valid = (not AUTH_REQUIRED) or (
                    hmac.compare_digest(username, AUTH_USERNAME)
                    and hmac.compare_digest(password, AUTH_PASSWORD)
                )
                if not valid:
                    raise ApiError(HTTPStatus.UNAUTHORIZED, "Invalid username or password.")
                token = create_session(AUTH_USERNAME)
                self.send_json(
                    HTTPStatus.OK,
                    auth_status(True, AUTH_USERNAME),
                    no_store=True,
                    extra_headers={"Set-Cookie": self.session_cookie(token)},
                )
            elif path == "/api/auth/logout":
                token = self.cookie_token()
                if token:
                    drop_session(token)
                self.send_json(
                    HTTPStatus.OK,
                    {"ok": True},
                    no_store=True,
                    extra_headers={"Set-Cookie": self.clear_session_cookie()},
                )
            elif path == "/api/upload":
                items = save_upload(self.headers, body)
                maybe_sync_index(force=True)
                self.send_json(HTTPStatus.CREATED, {"items": items})
            elif path == "/api/ai/suggest":
                payload = json.loads(body.decode("utf-8")) if body else {}
                self.send_json(HTTPStatus.OK, suggest_for_payload(payload))
            elif path == "/api/pipeline/process":
                payload = json.loads(body.decode("utf-8")) if body else {}
                rel = str(payload.get("path", ""))
                result = process_material(
                    rel,
                    create_source=bool(payload.get("create_source", True)),
                    archive=bool(payload.get("archive", True)),
                    overwrite_source=bool(payload.get("overwrite_source", False)),
                )
                self.send_json(HTTPStatus.OK, result)
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
            self.require_auth(path, "DELETE")
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
    print(f"AI provider: {active_ai_provider()}")
    print(f"Authentication required: {AUTH_REQUIRED}")
    server.serve_forever()


if __name__ == "__main__":
    main()
