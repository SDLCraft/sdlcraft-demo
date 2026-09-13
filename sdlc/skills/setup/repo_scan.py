"""Bounded evidence sweep over the project's own files, for the SDLC skills.

Only `prd` ever looked at the repository it was specifying. Every stage after
it read `docs/` and nothing else, so on a brownfield project the migrations,
route files, Dockerfiles and test layout already on disk contributed nothing to
DATA-MODEL, API, ARCH or TEST-STRATEGY. This helper is the shared eye: each
skill asks for its own domain and gets back a small, bounded set of candidate
signals with the file and line they came from.

What comes back is EVIDENCE, never an answer. A skill folds it into the Phase-3
pre-fill map tagged `inferred`, and the user confirms each item individually
(CLAUDE.md: inferred values are never batch-accepted). This matters most for
`arch`, where the structure that exists is not necessarily the structure the
project wants.

Cost discipline is the whole design. The file list comes from `git ls-files`
when the project is a git repo (exact .gitignore handling for free), the
per-domain file count and per-file byte count are capped, and an excerpt is one
trimmed line. Nothing here ever emits a file body.

Run from the project root:

    python .claude/sdlc/repo_scan.py --domain data
    python .claude/sdlc/repo_scan.py --domain arch --json
    python .claude/sdlc/repo_scan.py --list

Exit codes:
0 - the scan ran (finding nothing is a valid, common result)
2 - unknown domain, or the project root is unreadable
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HELPER_VERSION = "1"

# Cost caps. A scan that walks a monorepo unbounded costs more than the
# interview it is meant to inform.
MAX_FILES_SCANNED = 4000      # candidate paths considered, before per-domain filtering
MAX_HITS_PER_SIGNAL = 12      # a signal with 300 matches teaches nothing extra
MAX_BYTES_PER_FILE = 200_000  # skip anything larger; specs do not live in huge files
EXCERPT_CHARS = 120

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "env", ".env", ".tox", ".nox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build", "target", "out", ".next", ".nuxt", ".svelte-kit",
    "vendor", "site-packages", ".gradle", ".idea", ".vscode", ".terraform",
    "coverage", "htmlcov", ".cache", "bin", "obj",
}

SKIP_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Cargo.lock", "uv.lock", "composer.lock", "Gemfile.lock", "go.sum",
}

BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".tiff", ".avif",
    ".pdf", ".zip", ".gz", ".tar", ".bz2", ".xz", ".7z", ".rar",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".mp4", ".wav", ".ogg", ".webm", ".mov", ".avi",
    ".so", ".dylib", ".dll", ".exe", ".bin", ".o", ".a", ".class", ".jar",
    ".pyc", ".pyo", ".wasm", ".db", ".sqlite", ".sqlite3",
}


# =============================================================================
# The domain table
# =============================================================================
# One entry per skill. Each signal is {files: [glob...], contains: regex|None}:
#   contains is None -> the file EXISTING is the signal (line 1)
#   contains set     -> matching lines inside those files are the signal
# Globs match against the repo-relative POSIX path, so "**/x" is spelled "*/x"
# via fnmatch semantics on the full path - keep patterns anchored loosely.

DOMAINS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "prd": {
        "readme":        {"files": ["README*", "*/README*"], "contains": None},
        "manifests":     {"files": ["package.json", "pyproject.toml", "setup.py",
                                    "Cargo.toml", "go.mod", "pom.xml",
                                    "build.gradle*", "Gemfile", "composer.json",
                                    "*.csproj"], "contains": None},
        "idea_docs":     {"files": ["*idea*.md", "*vision*.md", "*pitch*.md",
                                    "*brief*.md", "BRD.yaml", "docs/*.md",
                                    "doc/*.md", "project/*.md"], "contains": None},
        "workspaces":    {"files": ["package.json"], "contains": r'"workspaces"'},
    },
    "ux": {
        "cli_parsers":   {"files": ["*.py"], "contains": r"\b(argparse\.ArgumentParser|import\s+click|from\s+typer|@click\.(command|group)|@app\.command)\b"},
        "cli_parsers_js": {"files": ["*.js", "*.ts", "*.mjs"], "contains": r"\b(commander|yargs|oclif)\b"},
        "cli_parsers_rs": {"files": ["*.rs"], "contains": r"\b(clap|StructOpt)\b"},
        "routes":        {"files": ["*/pages/*", "*/app/*/page.*", "*/routes/*",
                                    "*/router/*", "urls.py", "*/urls.py"], "contains": None},
        "templates":     {"files": ["*/templates/*.html", "*.hbs", "*.jinja",
                                    "*.jinja2", "*.ejs", "*.blade.php"], "contains": None},
        "components":    {"files": ["*/components/*.tsx", "*/components/*.jsx",
                                    "*/components/*.vue", "*/components/*.svelte"],
                          "contains": None},
        "i18n":          {"files": ["*/locales/*.json", "*/i18n/*", "*.po", "*.pot",
                                    "messages.json"], "contains": None},
    },
    "design": {
        "tailwind":      {"files": ["tailwind.config.*"], "contains": None},
        "token_files":   {"files": ["*tokens*.json", "*tokens*.yaml", "theme.json",
                                    "*/theme/*.ts", "*/theme/*.js"], "contains": None},
        "css_variables": {"files": ["*.css", "*.scss"], "contains": r"^\s*--[a-zA-Z0-9-]+\s*:"},
        "component_lib": {"files": ["components.json", "*/ui/*.tsx"], "contains": None},
        "fonts":         {"files": ["*/fonts/*", "*.woff2"], "contains": None},
        "asset_dirs":    {"files": ["assets/*", "public/*", "static/*",
                                    "*/assets/*"], "contains": None},
    },
    "data": {
        "migrations":    {"files": ["*/migrations/*.py", "*/migrations/*.sql",
                                    "*/versions/*.py", "db/migrate/*"], "contains": None},
        "prisma":        {"files": ["schema.prisma", "*/schema.prisma"], "contains": None},
        "sql_schema":    {"files": ["*.sql"], "contains": r"(?i)\bCREATE\s+TABLE\b"},
        "orm_models":    {"files": ["*.py"], "contains": r"^\s*class\s+\w+\((?:.*\b(?:Base|Model|BaseModel|Document|SQLModel)\b.*)\)"},
        "ts_models":     {"files": ["*.ts"], "contains": r"^\s*(?:export\s+)?(?:interface|type)\s+\w+\s*[={]"},
        "db_services":   {"files": ["docker-compose*.yml", "docker-compose*.yaml"],
                          "contains": r"(?i)\b(postgres|mysql|mariadb|mongo|redis|elasticsearch|clickhouse|neo4j)\b"},
    },
    "api": {
        "openapi":       {"files": ["openapi.*", "swagger.*", "*.openapi.*",
                                    "*/openapi/*"], "contains": None},
        "proto":         {"files": ["*.proto"], "contains": None},
        "graphql_sdl":   {"files": ["*.graphql", "*.gql"], "contains": None},
        "routes_py":     {"files": ["*.py"], "contains": r"@(?:app|router|bp|blueprint)\.(?:get|post|put|patch|delete|route)\("},
        "routes_js":     {"files": ["*.js", "*.ts"], "contains": r"\b(?:app|router)\.(?:get|post|put|patch|delete|use)\s*\("},
        "django_urls":   {"files": ["urls.py", "*/urls.py"], "contains": None},
    },
    "arch": {
        "manifests":     {"files": ["package.json", "pyproject.toml", "Cargo.toml",
                                    "go.mod", "pom.xml", "build.gradle*"], "contains": None},
        "dockerfiles":   {"files": ["Dockerfile*", "*/Dockerfile*"], "contains": None},
        "compose":       {"files": ["docker-compose*.yml", "docker-compose*.yaml"], "contains": None},
        "terraform":     {"files": ["*.tf"], "contains": None},
        "k8s":           {"files": ["*/k8s/*.yaml", "*/kubernetes/*.yaml",
                                    "*/helm/*", "*/charts/*"], "contains": None},
        "ci":            {"files": [".github/workflows/*", ".gitlab-ci.yml",
                                    "azure-pipelines.yml", "Jenkinsfile"], "contains": None},
        "procfile":      {"files": ["Procfile"], "contains": None},
    },
    "test": {
        "test_dirs":     {"files": ["tests/*", "test/*", "*/__tests__/*",
                                    "*/spec/*", "*_test.go"], "contains": None},
        "pytest_cfg":    {"files": ["pytest.ini", "conftest.py", "tox.ini"], "contains": None},
        "js_test_cfg":   {"files": ["jest.config.*", "vitest.config.*",
                                    "playwright.config.*", "cypress.config.*"], "contains": None},
        "coverage_cfg":  {"files": [".coveragerc", "codecov.yml", "*.coveragerc"], "contains": None},
        "fixtures":      {"files": ["*/fixtures/*", "*/factories/*"], "contains": None},
        "ci_test_jobs":  {"files": [".github/workflows/*"],
                          "contains": r"(?i)\b(pytest|jest|vitest|go test|cargo test|npm test)\b"},
    },
    "task": {
        "makefile":      {"files": ["Makefile", "makefile", "Taskfile.*", "justfile"], "contains": None},
        "npm_scripts":   {"files": ["package.json"], "contains": r'"scripts"'},
        "lint_cfg":      {"files": [".eslintrc*", "eslint.config.*", ".ruff.toml",
                                    ".flake8", ".pylintrc", "biome.json"], "contains": None},
        "format_cfg":    {"files": [".prettierrc*", ".editorconfig"], "contains": None},
        "precommit":     {"files": [".pre-commit-config.yaml"], "contains": None},
    },
}


# =============================================================================
# File discovery
# =============================================================================

def _git_files(root: Path) -> Optional[List[str]]:
    """Tracked + untracked-but-not-ignored paths, or None when not a git repo.

    Asking git is both cheaper and more accurate than walking: it applies the
    project's own .gitignore, which is exactly the "don't read build output"
    rule we would otherwise have to approximate.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--cached", "--others",
             "--exclude-standard"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]


def _walked_files(root: Path) -> List[str]:
    """Fallback for a non-git project: a pruned os.walk."""
    found: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS
                       and not d.startswith(".")]
        for name in filenames:
            rel = Path(dirpath, name).relative_to(root).as_posix()
            found.append(rel)
            if len(found) >= MAX_FILES_SCANNED * 2:
                return found
    return found


def candidate_files(root: Path) -> Tuple[List[str], bool]:
    """(repo-relative POSIX paths worth reading, truncated?)."""
    paths = _git_files(root)
    if paths is None:
        paths = _walked_files(root)
    keep: List[str] = []
    for rel in paths:
        parts = rel.split("/")
        if any(p in SKIP_DIRS for p in parts[:-1]):
            continue
        name = parts[-1]
        if name in SKIP_FILES:
            continue
        if Path(name).suffix.lower() in BINARY_SUFFIXES:
            continue
        keep.append(rel)
    # Shallow first. With a per-signal cap, ordering decides WHICH hits the
    # skill sees, and a root-level `tests/` or `Dockerfile` says more about the
    # project than the tenth copy of one inside a vendored or snapshot tree.
    keep.sort(key=lambda r: (r.count("/"), r))
    truncated = len(keep) > MAX_FILES_SCANNED
    return keep[:MAX_FILES_SCANNED], truncated


def _matches(rel: str, patterns: List[str]) -> bool:
    """fnmatch against both the full path and the bare filename.

    Matching the basename too is what lets a pattern like "Dockerfile*" find
    "services/api/Dockerfile" without every caller writing "*/Dockerfile*".
    """
    base = rel.rsplit("/", 1)[-1]
    for pat in patterns:
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(base, pat):
            return True
        if "/" in pat and fnmatch.fnmatch(rel, "*/" + pat.lstrip("*/")):
            return True
    return False


def _read_text(path: Path) -> Optional[str]:
    try:
        if path.stat().st_size > MAX_BYTES_PER_FILE:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _excerpt(line: str) -> str:
    s = " ".join(line.split())
    return s[:EXCERPT_CHARS]


# =============================================================================
# The scan
# =============================================================================

def scan(root: Path, domain: str) -> Dict[str, Any]:
    signals_spec = DOMAINS[domain]
    files, truncated = candidate_files(root)
    signals: Dict[str, List[Dict[str, Any]]] = {}
    capped: List[str] = []

    for key, spec in signals_spec.items():
        pats: List[str] = spec["files"]
        rx = re.compile(spec["contains"]) if spec.get("contains") else None
        hits: List[Dict[str, Any]] = []
        hit_cap_reached = False
        for rel in files:
            if not _matches(rel, pats):
                continue
            if rx is None:
                text = _read_text(root / rel)
                first = ""
                if text:
                    for ln in text.splitlines():
                        if ln.strip():
                            first = _excerpt(ln)
                            break
                hits.append({"path": rel, "line": 1, "excerpt": first})
            else:
                text = _read_text(root / rel)
                if text is None:
                    continue
                for i, ln in enumerate(text.splitlines(), start=1):
                    if rx.search(ln):
                        hits.append({"path": rel, "line": i, "excerpt": _excerpt(ln)})
                        break        # one hit per file: the file is the signal
            if len(hits) >= MAX_HITS_PER_SIGNAL:
                hit_cap_reached = True
                break
        if hits:
            signals[key] = hits
            if hit_cap_reached:
                capped.append(key)

    return {
        "domain": domain,
        "helper_version": HELPER_VERSION,
        "signals": signals,
        "scanned_files": len(files),
        "truncated": truncated,
        "capped_signals": capped,
        "evidence_tag": "inferred",
    }


# =============================================================================
# Reporting
# =============================================================================

def print_report(result: Dict[str, Any]) -> None:
    domain = result["domain"]
    signals = result["signals"]
    n_hits = sum(len(v) for v in signals.values())

    if not signals:
        print(f"[OK] nothing in this repo matches what /sdlc:{domain} looks for "
              f"({result['scanned_files']} file(s) checked) - the interview starts "
              f"from the upstream specs alone, which is normal on a new project.")
        print()
        print(f"NEXT: run /sdlc:{domain}.")
        return

    print(f"[OK] {n_hits} candidate(s) for /sdlc:{domain} across "
          f"{len(signals)} signal(s), from {result['scanned_files']} file(s) "
          f"checked. These are candidates to confirm, never answers.")
    print()
    for key, hits in signals.items():
        more = "  (more exist - only the first few are listed)" if key in result["capped_signals"] else ""
        print(f"{key} ({len(hits)}){more}:")
        for h in hits:
            where = f"{h['path']}:{h['line']}" if h["line"] > 1 else h["path"]
            print(f"  - {where}" + (f"   {h['excerpt']}" if h["excerpt"] else ""))
        print()

    if result["truncated"]:
        print(f"WARNINGS (1) - none of these block the next skill:")
        print(f"  - the repo is larger than this sweep reads "
              f"({MAX_FILES_SCANNED} file(s) max), so some evidence was not "
              f"looked at. Treat the list above as a sample, not an inventory.")
        print()

    print(f"NEXT: run /sdlc:{domain}; it folds these into its pre-fill map as "
          f"'inferred' and asks you to confirm each one.")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Bounded evidence sweep over the project's own files, "
                    "for one SDLC skill's domain.")
    ap.add_argument("--domain", help=f"one of: {', '.join(sorted(DOMAINS))}")
    ap.add_argument("--root", default=".", help="project root (default: cwd)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--list", action="store_true", dest="list_domains",
                    help="list the domains this helper knows")
    args = ap.parse_args(argv)

    if args.list_domains:
        for d in sorted(DOMAINS):
            print(f"{d}: {', '.join(DOMAINS[d])}")
        return 0

    if not args.domain:
        print("[FAIL] no domain given - pass --domain with one of: "
              f"{', '.join(sorted(DOMAINS))}", file=sys.stderr)
        return 2
    if args.domain not in DOMAINS:
        print(f"[FAIL] '{args.domain}' is not a domain this helper knows. "
              f"Valid: {', '.join(sorted(DOMAINS))}", file=sys.stderr)
        return 2

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"[FAIL] {root} is not a readable directory.", file=sys.stderr)
        return 2

    result = scan(root, args.domain)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_report(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
