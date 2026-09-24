#!/usr/bin/env python3
"""Which sdlc plugin is running - for a caller that has no ${CLAUDE_SKILL_DIR}.

Inside a skill run the plugin root is `${CLAUDE_SKILL_DIR}/../..`, and every
helper-resolution rule starts there. A SessionStart hook, a project's own
script or a CI job has neither that variable nor CLAUDE_PLUGIN_ROOT, so one
project hard-coded a marketplace path and measured with plugin 0.9.10 for ten
days after 0.9.17 was installed under another marketplace (done=34 where the
running plugin said 65). This script is the sanctioned answer: it reads the
registry Claude Code keeps and prints the newest ENABLED sdlc plugin.

Resolution order (first hit wins):

  1. $SDLC_PLUGIN_ROOT      an explicit override, for bisecting - the folder
                            must carry .claude-plugin/plugin.json.
  2. $CLAUDE_SKILL_DIR      inside a skill run: its ../.. is the plugin.
  3. the registry           <home>/plugins/installed_plugins.json -> plugins,
                            every key `sdlc@<marketplace>` (never one literal
                            marketplace); <home>/settings.json ->
                            enabledPlugins drops a key set to false (an
                            unreadable settings file keeps them all); the
                            highest version wins, compared part by part as
                            integers (0.10.0 > 0.9.14; a non-numeric version
                            sorts oldest); a candidate must carry
                            .claude-plugin/plugin.json AND
                            skills/setup/docs_index.py (present in every
                            edition); the version is read from that manifest,
                            the registry's is the fallback.

<home> is $CLAUDE_CONFIG_DIR, else ~/.claude, else --home.

Usage:
    python plugin_root.py            # "0.9.17 @ sdlcraft"
    python plugin_root.py --path     # the root folder alone, for a shell
    python plugin_root.py --json     # {root, version, marketplace, source, candidates}
    python plugin_root.py --home DIR # read another Claude home (tests)

Exit codes:
    0 - a plugin root was found.
    1 - no enabled sdlc plugin is registered (one line says where it looked).
    2 - the registry or a manifest could not be read or parsed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

__version__ = "1"

PLUGIN_NAME = "sdlc"
_KEY_RE = re.compile(r"^" + re.escape(PLUGIN_NAME) + r"@(?P<market>.+)$")
# What every edition of the plugin carries: the manifest, and setup's own
# generator. Never a Pro-only skill's file - the free edition has none.
_REQUIRED = (Path(".claude-plugin") / "plugin.json", Path("skills") / "setup" / "docs_index.py")


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass


def claude_home(override: Optional[str] = None) -> Path:
    if override:
        return Path(override).expanduser()
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".claude"


def version_key(version) -> "tuple[int, tuple[int, ...]]":
    """Sort key: (1, parts) for a dotted number, (0, ()) for anything else,
    so a `sha:` or a blank sorts below every real version."""
    try:
        return 1, tuple(int(p) for p in str(version).strip().split("."))
    except ValueError:
        return 0, ()


def manifest_version(root: Path) -> Optional[str]:
    try:
        data = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    version = data.get("version") if isinstance(data, dict) else None
    return str(version) if version else None


def is_plugin_root(root: Path) -> bool:
    return all((root / rel).is_file() for rel in _REQUIRED)


def read_registry(home: Path) -> "tuple[list[dict], Optional[str]]":
    """Every registered sdlc install as {marketplace, root, version, enabled},
    plus a problem string when the registry could not be read (a MISSING
    registry is not a problem - it means no plugin is installed)."""
    reg_path = home / "plugins" / "installed_plugins.json"
    if not reg_path.is_file():
        return [], None
    try:
        registry = json.loads(reg_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [], f"cannot read {reg_path}: {e}"
    plugins = registry.get("plugins") if isinstance(registry, dict) else None
    if not isinstance(plugins, dict):
        return [], f"{reg_path} has no plugins mapping"
    enabled = _enabled_map(home)
    out: list[dict] = []
    for key, value in plugins.items():
        m = _KEY_RE.match(str(key))
        if m is None:
            continue
        entries = value if isinstance(value, list) else [value]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            path = entry.get("installPath")
            if not path:
                continue
            out.append({
                "key": str(key),
                "marketplace": m.group("market"),
                "root": str(path),
                "registry_version": str(entry.get("version") or "") or None,
                "enabled": enabled.get(str(key), True),
            })
    return out, None


def _enabled_map(home: Path) -> "dict[str, bool]":
    """settings.json -> enabledPlugins. Only an explicit false disables; an
    absent key, or an unreadable file, keeps every install in play."""
    try:
        settings = json.loads((home / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    block = settings.get("enabledPlugins") if isinstance(settings, dict) else None
    if not isinstance(block, dict):
        return {}
    return {str(k): (v is not False) for k, v in block.items()}


def _describe(root: Path, source: str, candidates: "list[dict]",
              marketplace: Optional[str] = None) -> dict:
    version = manifest_version(root)
    if marketplace is None:
        resolved = str(root.resolve()).lower()
        for c in candidates:
            try:
                same = str(Path(c["root"]).resolve()).lower() == resolved
            except OSError:
                same = False
            if same:
                marketplace = c["marketplace"]
                if version is None:
                    version = c.get("registry_version")
                break
    return {"root": str(root), "version": version, "marketplace": marketplace or "unregistered",
            "source": source, "candidates": candidates}


def resolve(home: Path, env: "Optional[dict]" = None) -> "tuple[Optional[dict], Optional[str]]":
    """(result, problem). result is None when nothing resolves; problem is a
    sentence when the registry or an override is unusable."""
    env = os.environ if env is None else env
    candidates, problem = read_registry(home)
    override = env.get("SDLC_PLUGIN_ROOT")
    if override:
        root = Path(override).expanduser()
        if not is_plugin_root(root):
            return None, (f"SDLC_PLUGIN_ROOT={override} is not a plugin root (it needs "
                          f".claude-plugin/plugin.json and skills/setup/docs_index.py)")
        return _describe(root, "override", candidates), problem
    skill_dir = env.get("CLAUDE_SKILL_DIR")
    if skill_dir:
        root = Path(skill_dir).expanduser().parent.parent
        if is_plugin_root(root):
            return _describe(root, "skill-dir", candidates), problem
    if problem:
        return None, problem
    usable = []
    for c in candidates:
        if not c["enabled"]:
            continue
        root = Path(c["root"])
        if not is_plugin_root(root):
            continue
        c = dict(c)
        c["version"] = manifest_version(root) or c.get("registry_version")
        usable.append(c)
    if not usable:
        return None, None
    best = max(usable, key=lambda c: version_key(c.get("version")))
    return {"root": best["root"], "version": best.get("version"),
            "marketplace": best["marketplace"], "source": "registry",
            "candidates": candidates}, None


def render(result: dict) -> str:
    tag = {"override": " [override]", "skill-dir": " [skill dir]"}.get(result["source"], "")
    return f"{result.get('version') or '?'} @ {result['marketplace']}{tag}"


def main(argv=None) -> int:
    _force_utf8_stdio()
    ap = argparse.ArgumentParser(description="Print which sdlc plugin is running - the newest "
                                             "enabled install in Claude Code's plugin registry.")
    ap.add_argument("--home", default=None, help="the Claude home to read (default: "
                                                  "$CLAUDE_CONFIG_DIR, else ~/.claude)")
    ap.add_argument("--json", action="store_true", help="machine-readable result")
    ap.add_argument("--path", action="store_true", help="print the root folder alone")
    args = ap.parse_args(argv)
    home = claude_home(args.home)
    result, problem = resolve(home)
    if result is None:
        if problem:
            print(f"[FAIL] {problem}", file=sys.stderr)
            return 2
        print(f"[FAIL] no enabled sdlc plugin is registered in {home / 'plugins' / 'installed_plugins.json'} "
              f"- install one (claude plugin install sdlc@<marketplace>), or set SDLC_PLUGIN_ROOT",
              file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2))
    elif args.path:
        print(result["root"])
    else:
        print(render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
