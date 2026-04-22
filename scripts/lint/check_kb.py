#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WIKI_ROOT = REPO_ROOT / "wiki"
SOURCES_ROOT = WIKI_ROOT / "sources"
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
                errors.append(f"broken link: {path.relative_to(REPO_ROOT).as_posix()} -> {target}")
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


def split_level_two_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_heading: str | None = None
    current_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current_heading is not None:
                sections.append((current_heading, "\n".join(current_lines).strip()))
            current_heading = line[3:].strip()
            current_lines = []
            continue
        if current_heading is not None:
            current_lines.append(line)
    if current_heading is not None:
        sections.append((current_heading, "\n".join(current_lines).strip()))
    return sections


def count_field_bullets(section_text: str) -> int:
    count = 0
    for line in section_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and re.search(r"[:\uFF1A]", stripped):
            count += 1
    return count


def count_plain_bullets(section_text: str) -> int:
    return sum(1 for line in section_text.splitlines() if line.strip().startswith("- "))


def has_summary_paragraph(section_text: str) -> bool:
    for line in section_text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(("- ", "* ", "#")):
            return True
    return False


def check_source_pages(errors: list[str]) -> int:
    checked = 0
    if not SOURCES_ROOT.exists():
        return checked
    for path in sorted(SOURCES_ROOT.glob("*.md")):
        checked += 1
        rel = path.relative_to(REPO_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        sections = split_level_two_sections(text)
        if len(sections) < 3:
            errors.append(f"source page missing sections: {rel} -> need at least 3 level-2 sections")
            continue
        basic_info_body = sections[0][1]
        summary_body = sections[1][1]
        key_points_body = sections[2][1]
        if count_field_bullets(basic_info_body) < 4:
            errors.append(f"source page basic info too thin: {rel} -> need at least 4 field bullets")
        if "raw/" not in basic_info_body:
            errors.append(f"source page missing raw path link: {rel}")
        if not has_summary_paragraph(summary_body):
            errors.append(f"source page missing summary paragraph: {rel}")
        if count_plain_bullets(key_points_body) < 3:
            errors.append(f"source page key points too thin: {rel} -> need at least 3 bullets")
    return checked


def main() -> int:
    errors: list[str] = []
    markdown_files = collect_markdown_files()
    check_required_files(errors)
    link_count = check_relative_links(markdown_files, errors)
    missing_entries = check_index_coverage(errors)
    source_page_count = check_source_pages(errors)

    print(f"repo_root={REPO_ROOT}")
    print(f"markdown_files={len(markdown_files)}")
    print(f"relative_links_checked={link_count}")
    print(f"missing_index_entries={len(missing_entries)}")
    print(f"source_pages_checked={source_page_count}")

    if errors:
        print("status=failed")
        for item in errors:
            print(f"ERROR: {item}")
        return 1

    print("status=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
