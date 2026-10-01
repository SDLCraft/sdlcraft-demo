"""Deterministic quality floors for a DESIGN__tokens.yaml (sdlc-design).

Run from the project root:

    python sdlc/skills/design/design_lint.py
    python sdlc/skills/design/design_lint.py --path docs/DESIGN__tokens.yaml
    python sdlc/skills/design/design_lint.py --json

Why it exists: a language model cannot reliably compute a WCAG contrast ratio
or count the hue families in a palette by eye, so "the palette meets AA" was
an unverified claim. This script makes the measurable half of the design
review (references/merge-validate.md -> "Pre-write design review") a
computation. The judgement half (is the bold dimension actually bold? does
the direction read as its mood keywords?) stays with the agent.

Checks, each finding classed blocker | quality | polish:

    contrast      every `contrast_pairs` entry, per theme mode, against its
                  minimum (text 4.5, large_text 3.0, ui 3.0, focus 3.0, or the
                  pair's own higher `min`). Below the minimum = blocker.
    contrast-set  no `contrast_pairs` declared at all = quality (the claim in
                  `contrast_notes` is unverified).
    hues          more than 5 distinct non-semantic hue families = quality.
                  Neutrals (low saturation) and semantic paths
                  (success/warning/error/danger/info/...) are not counted.
    pure-bw       a colour token resolving to exactly #000000 or #ffffff =
                  quality (toned near-black / near-white is the default; pure
                  values are fine as a stated choice).
    fonts         more than 2 non-monospace font families = quality.
    spacing       a spacing value not on a 4px grid (0-2px hairlines exempt)
                  = quality.
    radius        more than 5 distinct finite radius values = polish.
    state         no `state` token group (interaction states) = quality.

Colour values understood: #rgb, #rrggbb, #rrggbbaa (alpha ignored, reported),
rgb()/rgba(), hsl()/hsla(), oklch(), and DTCG colour objects
{colorSpace: srgb, components: [r, g, b]}. Aliases `{group.path}` resolve
recursively. Per-mode values live in a leaf's `$extensions.modes.<mode>`;
a leaf without one uses its `$value` in every mode.

Exit codes:
    0 - no blocker (quality / polish findings may still be listed).
    1 - at least one blocker (a contrast pair below its minimum, or an
        unresolvable pair).
    2 - could not read or parse the file.
    3 - required dependency missing (pyyaml).
"""

from __future__ import annotations

import argparse
import colorsys
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - exercised only without pyyaml
    print("ERROR: pyyaml is required: pip install pyyaml", file=sys.stderr)
    raise SystemExit(3)


RGB = Tuple[float, float, float]

# WCAG 2.x minimums by use. A pair may raise its own minimum (e.g. 7.0 for
# AAA text) but never lower it below these.
MIN_RATIO: Dict[str, float] = {
    "text": 4.5,
    "large_text": 3.0,
    "ui": 3.0,
    "focus": 3.0,
}

SEMANTIC_PATH_RE = re.compile(
    r"(success|positive|valid|warning|warn|caution|error|danger|destructive|"
    r"negative|invalid|critical|info|notice)",
    re.IGNORECASE,
)
ALIAS_RE = re.compile(r"^\{([^{}]+)\}$")
MAX_HUE_FAMILIES = 5
MAX_FONT_FAMILIES = 2
MAX_RADII = 5
NEUTRAL_SATURATION = 0.12


# =============================================================================
# Colour parsing + WCAG maths
# =============================================================================


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def _num(token: str, scale: float = 1.0) -> float:
    token = token.strip()
    if token.endswith("%"):
        return float(token[:-1]) / 100.0 * scale
    return float(token)


def _oklch_to_srgb(l: float, c: float, h_deg: float) -> RGB:
    h = math.radians(h_deg)
    a, b = c * math.cos(h), c * math.sin(h)
    l_ = l + 0.3963377774 * a + 0.2158037573 * b
    m_ = l - 0.1055613458 * a - 0.0638541728 * b
    s_ = l - 0.0894841775 * a - 1.2914855480 * b
    lc, mc, sc = l_ ** 3, m_ ** 3, s_ ** 3
    lin = (
        4.0767416621 * lc - 3.3077115913 * mc + 0.2309699292 * sc,
        -1.2684380046 * lc + 2.6097574011 * mc - 0.3413193965 * sc,
        -0.0041960863 * lc - 0.7034186147 * mc + 1.7076147010 * sc,
    )

    def enc(v: float) -> float:
        v = _clamp01(v)
        return 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055

    return (enc(lin[0]), enc(lin[1]), enc(lin[2]))


def parse_color(value: Any) -> Tuple[Optional[RGB], Optional[str]]:
    """Return ((r, g, b) in 0..1, note) or (None, reason)."""
    if isinstance(value, dict):
        comps = value.get("components")
        space = str(value.get("colorSpace") or "srgb").lower()
        if space == "srgb" and isinstance(comps, list) and len(comps) >= 3:
            try:
                return (tuple(_clamp01(float(c)) for c in comps[:3]), None)  # type: ignore[return-value]
            except (TypeError, ValueError):
                return (None, f"unreadable colour components {comps!r}")
        if isinstance(value.get("hex"), str):
            return parse_color(value["hex"])
        return (None, f"unsupported colour object (colorSpace {space})")
    if not isinstance(value, str):
        return (None, f"not a colour value: {value!r}")
    s = value.strip().lower()
    m = re.fullmatch(r"#([0-9a-f]{3,8})", s)
    if m:
        hx = m.group(1)
        if len(hx) in (3, 4):
            hx = "".join(ch * 2 for ch in hx)
        if len(hx) not in (6, 8):
            return (None, f"bad hex colour {value!r}")
        rgb = tuple(int(hx[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
        note = "alpha ignored" if len(hx) == 8 and hx[6:] != "ff" else None
        return (rgb, note)  # type: ignore[return-value]
    m = re.fullmatch(r"(rgba?|hsla?|oklch)\(([^)]*)\)", s)
    if not m:
        return (None, f"unsupported colour syntax {value!r}")
    fn, args = m.group(1), re.split(r"[\s,/]+", m.group(2).strip())
    try:
        if fn.startswith("rgb"):
            rgb = tuple(_clamp01(_num(a, 255.0) / 255.0) for a in args[:3])
            return (rgb, "alpha ignored" if len(args) > 3 else None)  # type: ignore[return-value]
        if fn.startswith("hsl"):
            h = float(args[0].replace("deg", "")) / 360.0
            sat, lig = _num(args[1]), _num(args[2])
            r, g, b = colorsys.hls_to_rgb(h % 1.0, lig, sat)
            return ((r, g, b), "alpha ignored" if len(args) > 3 else None)
        l = _num(args[0])
        c = _num(args[1], 0.4)
        h = float(args[2].replace("deg", ""))
        return (_oklch_to_srgb(l, c, h), "alpha ignored" if len(args) > 3 else None)
    except (ValueError, IndexError):
        return (None, f"unreadable colour {value!r}")


def relative_luminance(rgb: RGB) -> float:
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: RGB, bg: RGB) -> float:
    a, b = relative_luminance(fg), relative_luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


# =============================================================================
# Token tree: flatten, resolve aliases, per-mode values
# =============================================================================


def _is_leaf(node: Any) -> bool:
    return isinstance(node, dict) and "$value" in node


def flatten(tree: Any, prefix: str = "") -> Dict[str, Dict[str, Any]]:
    """Map dotted path -> leaf mapping for every `$value` leaf under `tree`."""
    out: Dict[str, Dict[str, Any]] = {}
    if _is_leaf(tree):
        out[prefix] = tree
        return out
    if isinstance(tree, dict):
        for k, v in tree.items():
            if str(k).startswith("$"):
                continue
            path = f"{prefix}.{k}" if prefix else str(k)
            out.update(flatten(v, path))
    return out


class TokenSet:
    def __init__(self, doc: Dict[str, Any]):
        self.doc = doc
        self.leaves: Dict[str, Dict[str, Any]] = {}
        for group, body in doc.items():
            if group in ("metadata", "contrast_pairs") or not isinstance(body, dict):
                continue
            self.leaves.update(flatten(body, str(group)))
        modes = doc.get("theme_modes")
        self.modes: List[str] = [str(m) for m in modes] if isinstance(modes, list) else []

    @staticmethod
    def _mode_value(leaf: Dict[str, Any], mode: Optional[str]) -> Any:
        if mode:
            ext = leaf.get("$extensions")
            if isinstance(ext, dict):
                modes = ext.get("modes")
                if isinstance(modes, dict) and mode in modes:
                    return modes[mode]
        return leaf.get("$value")

    def has_mode_values(self, path: str) -> bool:
        leaf = self.leaves.get(path)
        ext = leaf.get("$extensions") if leaf else None
        return isinstance(ext, dict) and isinstance(ext.get("modes"), dict)

    def resolve(self, ref: str, mode: Optional[str], _seen: Optional[set] = None) -> Tuple[Any, Optional[str]]:
        """Resolve a path or `{alias}` to a raw value for `mode`. (value, error)."""
        seen = _seen or set()
        path = ref.strip()
        m = ALIAS_RE.match(path)
        if m:
            path = m.group(1).strip()
        if path in seen:
            return (None, f"alias cycle at {path}")
        seen.add(path)
        leaf = self.leaves.get(path)
        if leaf is None:
            return (None, f"no token at {path}")
        val = self._mode_value(leaf, mode)
        if isinstance(val, str) and ALIAS_RE.match(val.strip()):
            return self.resolve(val, mode, seen)
        return (val, None)

    def alias_chain_has_modes(self, ref: str) -> bool:
        path = ref.strip()
        seen: set = set()
        while True:
            m = ALIAS_RE.match(path)
            if m:
                path = m.group(1).strip()
            if path in seen or path not in self.leaves:
                return False
            seen.add(path)
            if self.has_mode_values(path):
                return True
            val = self.leaves[path].get("$value")
            if not (isinstance(val, str) and ALIAS_RE.match(val.strip())):
                return False
            path = val


# =============================================================================
# Checks
# =============================================================================


def _finding(severity: str, check: str, where: str, message: str) -> Dict[str, str]:
    return {"severity": severity, "check": check, "where": where, "message": message}


def check_contrast(ts: TokenSet) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
    findings: List[Dict[str, str]] = []
    measured: List[Dict[str, Any]] = []
    pairs = ts.doc.get("contrast_pairs")
    if not pairs:
        findings.append(_finding(
            "quality", "contrast-set", "contrast_pairs",
            "no contrast_pairs are declared, so nothing proves the palette meets "
            "its contrast target - list the text-on-surface, semantic-on-surface "
            "and focus-ring pairs you rely on"))
        return findings, measured
    if not isinstance(pairs, list):
        findings.append(_finding("blocker", "contrast", "contrast_pairs",
                                 "contrast_pairs must be a list of {fg, bg, use}"))
        return findings, measured
    for i, pair in enumerate(pairs):
        where = f"contrast_pairs[{i}]"
        if not isinstance(pair, dict) or not pair.get("fg") or not pair.get("bg"):
            findings.append(_finding("blocker", "contrast", where,
                                     "each pair needs fg and bg token references"))
            continue
        use = str(pair.get("use") or "text")
        floor = MIN_RATIO.get(use)
        if floor is None:
            findings.append(_finding("blocker", "contrast", where,
                                     f"use '{use}' is not one of {sorted(MIN_RATIO)}"))
            continue
        target = floor
        if pair.get("min") is not None:
            try:
                target = float(pair["min"])
            except (TypeError, ValueError):
                findings.append(_finding("blocker", "contrast", where,
                                         f"min {pair['min']!r} is not a number"))
                continue
            if target < floor:
                findings.append(_finding(
                    "quality", "contrast", where,
                    f"min {target} is below the WCAG AA minimum {floor} for {use}; "
                    f"checked against {floor} instead"))
                target = floor
        fg, bg = str(pair["fg"]), str(pair["bg"])
        if pair.get("mode"):
            modes: List[Optional[str]] = [str(pair["mode"])]
        elif ts.modes and (ts.alias_chain_has_modes(fg) or ts.alias_chain_has_modes(bg)):
            modes = list(ts.modes)
        else:
            modes = [None]
        for mode in modes:
            label = f"{where} ({mode})" if mode else where
            fv, ferr = ts.resolve(fg, mode)
            bv, berr = ts.resolve(bg, mode)
            if ferr or berr:
                findings.append(_finding("blocker", "contrast", label,
                                         f"cannot resolve: {ferr or berr}"))
                continue
            frgb, fnote = parse_color(fv)
            brgb, bnote = parse_color(bv)
            if frgb is None or brgb is None:
                findings.append(_finding("blocker", "contrast", label,
                                         f"cannot read colour: {fnote if frgb is None else bnote}"))
                continue
            ratio = contrast_ratio(frgb, brgb)
            ok = ratio + 1e-9 >= target
            measured.append({"pair": label, "fg": fg, "bg": bg, "use": use,
                             "ratio": round(ratio, 2), "min": target, "pass": ok})
            if not ok:
                findings.append(_finding(
                    "blocker", "contrast", label,
                    f"{fg} on {bg} is {ratio:.2f}:1, below the {target}:1 needed "
                    f"for {use.replace('_', ' ')}"))
            for note in (fnote, bnote):
                if note:
                    findings.append(_finding("polish", "contrast", label,
                                             f"{note}; ratio computed as if opaque"))
    return findings, measured


def _hue_families(hues: List[float]) -> int:
    """Count clusters of hues (degrees) where neighbours sit < 20 deg apart."""
    if not hues:
        return 0
    hs = sorted(h % 360.0 for h in hues)
    gaps = [(hs[(i + 1) % len(hs)] - hs[i]) % 360.0 for i in range(len(hs))]
    if len(hs) == 1:
        return 1
    return max(1, sum(1 for g in gaps if g >= 20.0))


def check_palette(ts: TokenSet) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    hues: List[float] = []
    for path, leaf in sorted(ts.leaves.items()):
        if not path.startswith("color."):
            continue
        val, err = ts.resolve(path, None)
        if err:
            continue
        rgb, _ = parse_color(val)
        if rgb is None:
            continue
        hexed = "#%02x%02x%02x" % tuple(round(c * 255) for c in rgb)
        if hexed in ("#000000", "#ffffff") and not ALIAS_RE.match(str(leaf.get("$value", "")).strip()):
            findings.append(_finding(
                "quality", "pure-bw", path,
                f"{hexed} is pure {'black' if hexed == '#000000' else 'white'} - a "
                f"toned near-{'black' if hexed == '#000000' else 'white'} reads "
                f"less harsh; keep it only as a stated choice"))
        if SEMANTIC_PATH_RE.search(path):
            continue
        h, _l, s = colorsys.rgb_to_hls(*rgb)
        if s >= NEUTRAL_SATURATION and 0.08 < _l < 0.95:
            hues.append(h * 360.0)
    n = _hue_families(hues)
    if n > MAX_HUE_FAMILIES:
        findings.append(_finding(
            "quality", "hues", "color",
            f"{n} distinct hue families outside the semantic colours (more than "
            f"{MAX_HUE_FAMILIES} reads as arbitrary) - consolidate onto one "
            f"primary, at most one accent, and neutrals"))
    return findings


def _font_names(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(value[0])] if value else []
    if isinstance(value, str):
        return [value.split(",")[0]]
    return []


def check_fonts(ts: TokenSet) -> List[Dict[str, str]]:
    families: Dict[str, str] = {}
    for path, leaf in ts.leaves.items():
        if not path.startswith("typography."):
            continue
        is_family = str(leaf.get("$type") or "") == "fontFamily" or re.search(
            r"famil", path, re.IGNORECASE)
        if not is_family:
            continue
        val, err = ts.resolve(path, None)
        if err:
            continue
        for name in _font_names(val):
            key = name.strip().strip("'\"").lower()
            if key and "mono" not in key:
                families.setdefault(key, path)
    if len(families) > MAX_FONT_FAMILIES:
        return [_finding(
            "quality", "fonts", "typography",
            f"{len(families)} font families ({', '.join(sorted(families))}) - more "
            f"than {MAX_FONT_FAMILIES} (monospace aside) feels chaotic; pair one "
            f"display face with one text face")]
    return []


def _px(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict) and "value" in value:
        unit = str(value.get("unit") or "px")
        try:
            v = float(value["value"])
        except (TypeError, ValueError):
            return None
        return v * 16.0 if unit == "rem" else v if unit == "px" else None
    if isinstance(value, str):
        m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*(px|rem)?\s*", value)
        if m:
            v = float(m.group(1))
            return v * 16.0 if m.group(2) == "rem" else v
    return None


def check_scales(ts: TokenSet) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    radii: set = set()
    for path in sorted(ts.leaves):
        group = path.split(".", 1)[0]
        if group not in ("spacing", "radius"):
            continue
        val, err = ts.resolve(path, None)
        if err:
            continue
        px = _px(val)
        if px is None:
            continue
        if group == "spacing" and px > 2 and abs(px / 4.0 - round(px / 4.0)) > 1e-6:
            findings.append(_finding(
                "quality", "spacing", path,
                f"{px:g}px is off the 4px grid - keep spacing on multiples of 4 "
                f"so rhythm stays consistent"))
        if group == "radius" and px < 999:
            radii.add(round(px, 2))
    if len(radii) > MAX_RADII:
        findings.append(_finding(
            "polish", "radius", "radius",
            f"{len(radii)} distinct radius values - 3 to {MAX_RADII} read as one system"))
    return findings


def check_state(ts: TokenSet) -> List[Dict[str, str]]:
    if isinstance(ts.doc.get("state"), dict) and ts.doc["state"]:
        return []
    return [_finding(
        "quality", "state", "state",
        "no state token group - hover, active, focus ring, disabled and transition "
        "values are left for each screen to invent")]


def lint(doc: Dict[str, Any]) -> Dict[str, Any]:
    ts = TokenSet(doc)
    contrast_findings, measured = check_contrast(ts)
    findings = (contrast_findings + check_palette(ts) + check_fonts(ts)
                + check_scales(ts) + check_state(ts))
    order = {"blocker": 0, "quality": 1, "polish": 2}
    findings.sort(key=lambda f: (order[f["severity"]], f["check"], f["where"]))
    return {"findings": findings, "contrast": measured}


# =============================================================================
# CLI
# =============================================================================


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check a DESIGN__tokens.yaml against the design quality floors.")
    parser.add_argument("--path", type=Path, default=Path("docs", "DESIGN__tokens.yaml"),
                        help="tokens file (default: ./docs/DESIGN__tokens.yaml)")
    parser.add_argument("--json", action="store_true",
                        help="print the machine-readable report instead of the summary")
    args = parser.parse_args(argv)
    try:
        doc = yaml.safe_load(args.path.read_text(encoding="utf-8"))
    except OSError as e:
        print(f"ERROR: cannot read {args.path}: {e}", file=sys.stderr)
        return 2
    except yaml.YAMLError as e:
        print(f"ERROR: {args.path} is not valid YAML: {e}", file=sys.stderr)
        return 2
    if not isinstance(doc, dict):
        print(f"ERROR: {args.path} does not hold a mapping", file=sys.stderr)
        return 2
    report = lint(doc)
    blockers = [f for f in report["findings"] if f["severity"] == "blocker"]
    if args.json:
        print(json.dumps(report, indent=2))
        return 1 if blockers else 0
    if blockers:
        print(f"[FAIL] {args.path}: {len(blockers)} thing(s) must be fixed before "
              f"this palette can be called accessible.")
    else:
        print(f"[OK] {args.path}: no contrast failures.")
    for m in report["contrast"]:
        mark = "pass" if m["pass"] else "FAIL"
        print(f"  {mark}  {m['ratio']:>5}:1 (needs {m['min']})  {m['pair']}  {m['fg']} on {m['bg']}")
    for sev, header in (("blocker", "MUST FIX"), ("quality", "WARNINGS"), ("polish", "POLISH")):
        rows = [f for f in report["findings"] if f["severity"] == sev]
        if rows:
            print(f"\n{header}")
            for f in rows:
                print(f"  - {f['where']}: {f['message']}")
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
