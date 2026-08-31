#!/usr/bin/env python3
"""Scan the repo for leftover sensitive strings (personal info, secrets) and exit 1 with
file:line:match for every hit, 0 if clean.

Two rule sources:
- INLINE rules below are generic and non-identifying (secret-key shapes, personal-email,
  money amounts). They are safe to publish, so this file scans itself too.
- Project-specific terms (usernames, employer/product/domain names) live in an untracked
  local file `.sanitize-terms.txt` (one Python regex per line, `#` comments allowed). It is
  git-ignored on purpose: enumerating those names *in a committed file* would itself be the
  leak this gate exists to prevent. Absent that file (e.g. on a fresh clone or in CI), only
  the inline rules run.
"""
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
TERMS_FILE = os.path.join(REPO_ROOT, ".sanitize-terms.txt")

# (label, compiled regex) -- generic, non-identifying, safe to show publicly.
FORBIDDEN = [
    ("personal-email", re.compile(r"@gmail\.com", re.IGNORECASE)),
    ("money-yen", re.compile(r"￥\s?\d")),
    ("openai-key", re.compile(r"sk-[A-Za-z0-9]{8}")),
    ("google-key", re.compile(r"AIza[0-9A-Za-z_-]{10}")),
    ("xai-key", re.compile(r"xai-[A-Za-z0-9]{8}")),
    ("nvidia-key", re.compile(r"nvapi-[A-Za-z0-9]{8}")),
    ("github-token", re.compile(r"ghp_[A-Za-z0-9]{8}")),
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]


def load_local_terms():
    """Add project-specific patterns from the untracked terms file, if present."""
    if not os.path.exists(TERMS_FILE):
        return
    with open(TERMS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            term = line.strip()
            if not term or term.startswith("#"):
                continue
            FORBIDDEN.append(("local-term", re.compile(term, re.IGNORECASE)))


EXCLUDE_DIRS = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules"}

TEXT_EXTS = {
    ".py", ".md", ".json", ".txt", ".yml", ".yaml", ".cfg", ".ini",
    ".sh", ".bat", ".ps1", ".gitignore", ".toml",
}


def is_text_file(path):
    _, ext = os.path.splitext(path)
    if ext in TEXT_EXTS:
        return True
    # Files with no extension (e.g. LICENSE) -- still try as text.
    return ext == ""


def scan_file(path):
    hits = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for lineno, line in enumerate(f, start=1):
                for label, rx in FORBIDDEN:
                    m = rx.search(line)
                    if m:
                        hits.append((path, lineno, label, m.group(0)))
    except OSError as e:
        print(f"WARN: could not read {path}: {e}", file=sys.stderr)
    return hits


def main():
    # Windows console (cp932) cannot print some matched characters; force UTF-8
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_local_terms()
    all_hits = []
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            # The terms file is git-ignored, but skip it defensively so a local run never
            # reports its own term list as hits.
            if os.path.abspath(fpath) == TERMS_FILE:
                continue
            if not is_text_file(fpath):
                continue
            all_hits.extend(scan_file(fpath))

    if all_hits:
        for path, lineno, label, match in all_hits:
            rel = os.path.relpath(path, REPO_ROOT)
            print(f"{rel}:{lineno}: [{label}] {match!r}")
        print(f"\n{len(all_hits)} forbidden-pattern hit(s) found.", file=sys.stderr)
        return 1

    print("clean: no forbidden patterns found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
