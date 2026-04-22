#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WIKI_ROOT = REPO_ROOT / "wiki"
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
REQUIRED_FILES = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "AGENTS.md",
    WIKI_ROOT / "index.md",
    WIKI_ROOT / "log.md",
    WIKI_ROOT / "overview.md",
]
INDEX_TRACKED_DIRS = [
    WIKI_ROOT / "projects",
    WIKI_ROOT / "topics",
    WIKI_ROOT / "concepts",
    WIKI_ROOT / "methods",
    WIKI_ROOT / "decisions",
    WIKI_ROOT / "sources",
    WIKI_ROOT / "reviews",
]


def is_ignored_target(target: str) -> bool:
    return target.startswith(("http://", "https://", "mailto:", "#"))


def collect_markdown_files() -> list[Path]:
    return sorted(path for path in REPO_ROOT.rglob("*.md") if ".git" not in path.parts)


def check_required_files(errors: list[str]) -> None:
    for path in REQUIRED_FILES:
        if not path.exists():
            errors.append(f"missing required file: {path.relative_to(REPO_ROOT).as_posix()}")


def check_relative_links(markdown_files: list[Path], errors: list[str]) -> int:
    checked = 0
    for path in markdown_files:
        text = path.read_text(encoding="utf-8")
        for target in LINK_RE.findall(text):
            if is_ignored_target(target):
                continue
            checked += 1
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                errors.append(
                    f"broken link: {path.relative_to(REPO_ROOT).as_posix()} -> {target}"
                )
    return checked


def check_index_coverage(errors: list[str]) -> list[str]:
    index_path = WIKI_ROOT / "index.md"
    if not index_path.exists():
        return []
    index_text = index_path.read_text(encoding="utf-8")
    missing_entries: list[str] = []
    for directory in INDEX_TRACKED_DIRS:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            rel = path.relative_to(WIKI_ROOT).as_posix()
            if rel not in index_text:
                missing_entries.append(rel)
                errors.append(f"missing index entry: {rel}")
    return missing_entries


def main() -> int:
    errors: list[str] = []
    markdown_files = collect_markdown_files()
    check_required_files(errors)
    link_count = check_relative_links(markdown_files, errors)
    missing_entries = check_index_coverage(errors)

    print(f"repo_root={REPO_ROOT}")
    print(f"markdown_files={len(markdown_files)}")
    print(f"relative_links_checked={link_count}")
    print(f"missing_index_entries={len(missing_entries)}")

    if errors:
        print("status=failed")
        for item in errors:
            print(f"ERROR: {item}")
        return 1

    print("status=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
