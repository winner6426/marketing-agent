"""Locks the migration rules: English-only source and no agent tooling in the repository."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent

# content_locale holds the vocabulary of generated ads and the GSM alphabet; samples holds test inputs.
VIETNAMESE_ALLOWED = {"src/content_locale.py", "tests/samples.py"}

# Vietnamese letters, written as escapes so this file stays clean under its own rule.
_VIETNAMESE_LETTERS = re.compile("[À-ÃÈ-ÊÌÍÒ-ÕÙÚÝ"
                                 "à-ãè-êìíò-õùúý"
                                 "ĂăĐđĨĩŨũƠơƯư"
                                 "Ạ-ỹ]")

# Accent-free Vietnamese identifiers the old codebase used.
_VIETNAMESE_IDENTIFIERS = re.compile(
    r"\b(?:tang[123]|kem_pin|thue_pin|tieu_chuan|loi_writer|vi_pham|noi_dung|chien_dich|kiem_dinh|bien_the|"
    r"thong_diep|chi_tiet|khoa|kenh|lich_dang|cho_nguoi|cho_duyet|hoi_lai|buoc_hien_tai|danh_gia|trich_dan|"
    r"bam_nguon|giong_nguoi|thuyet_phuc|mach_lac|dac_sac|boc_du_lieu|dau_thoi_gian|doi_role|xuat_ban|duyet)\b"
)

# Internal references to the old project's documents.
_LEGACY_REFERENCES = re.compile(r"\bP-201\b|\bPLO \d|\bP0-\d|invariant #\d|decision #\d", re.IGNORECASE)

FORBIDDEN_TOOLING = (
    ".agents",
    ".ai-log",
    ".claude",
    ".codex",
    ".cursor",
    ".gemini",
    ".mcp.json",
    "AGENTS.md",
    "CLAUDE.md",
)
IGNORED_DIRECTORIES = {".git", ".venv", "__pycache__", ".ruff_cache", ".pytest_cache", "data"}


def _project_files() -> list[Path]:
    return [
        path
        for path in REPOSITORY_ROOT.rglob("*")
        if path.is_file() and not IGNORED_DIRECTORIES.intersection(path.relative_to(REPOSITORY_ROOT).parts)
    ]


def _relative_to_backend(path: Path) -> str:
    return path.relative_to(BACKEND_ROOT).as_posix() if path.is_relative_to(BACKEND_ROOT) else path.name


def test_no_agent_tooling_in_repository():
    names = {part for path in _project_files() for part in path.relative_to(REPOSITORY_ROOT).parts}
    assert names.isdisjoint(FORBIDDEN_TOOLING)


def test_project_files_are_english():
    offenders = []
    for path in _project_files():
        if path == Path(__file__).resolve() or path.suffix not in {".py", ".md", ".toml", ".txt", ".example", ".yml"}:
            continue
        if _relative_to_backend(path) in VIETNAMESE_ALLOWED:
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in (_VIETNAMESE_LETTERS, _VIETNAMESE_IDENTIFIERS, _LEGACY_REFERENCES):
            if match := pattern.search(text):
                offenders.append(f"{path.name}: {match.group()!r}")
    assert offenders == []


def test_file_names_are_english():
    assert [path.name for path in _project_files() if _VIETNAMESE_LETTERS.search(path.name)] == []


@pytest.mark.parametrize("relative_path", sorted(VIETNAMESE_ALLOWED))
def test_vietnamese_exceptions_still_need_to_exist(relative_path):
    assert (BACKEND_ROOT / relative_path).is_file()


def _docstrings(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if docstring := ast.get_docstring(node):
                yield getattr(node, "name", "module"), docstring


@pytest.mark.parametrize("path", sorted((BACKEND_ROOT / "src").rglob("*.py")), ids=lambda path: path.name)
def test_docstrings_are_short(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    too_long = [
        name
        for name, docstring in _docstrings(tree)
        if len([line for line in docstring.splitlines() if line.strip()]) > 2
    ]
    assert too_long == []
