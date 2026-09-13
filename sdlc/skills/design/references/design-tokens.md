# Design tokens — authoring the DTCG set

Read this before **theme 3 (`design_tokens`)**, which runs only when
`token_based_ui` ∈ `functional_structure`. Output: `docs/DESIGN__tokens.yaml`,
the concrete token set a downstream coding agent compiles into CSS variables /
tailwind.config / a theme file. This is the real value-add over UX, which only
recorded the *decision* to use tokens; here we produce the *values*.

## DTCG shape primer

Token **groups** (`color`, `typography`, `spacing`, …) follow the W3C Design
Tokens Community Group format. A leaf token is a mapping with `$value` + `$type`;
groups nest; tokens may alias another by reference `{group.path}`:

```yaml
color:
  blue:
    "500": { "$value": "#2563eb", "$type": color }
  semantic:
    primary: { "$value": "{color.blue.500}", "$type": color }
spacing:
  "4": { "$value": "16px", "$type": dimension }
```

Keep the DTCG shape even when hand-authoring — it is what makes the set portable
and deterministically compilable. The validator type-checks each group as a
free-form mapping (it does NOT enforce the internal DTCG shape), so authored
sets, imported presets, and partial drafts all validate; the shape discipline is
on you.

## Step 1 — token_source: import or author

Ask `token_source` first — it forks the whole theme:

- **`import_shadcn` / `import_tailwind` / `import_tokens_studio` / `import_other`**
  → ask `imported_from` (the theme name / URL / file path). Pull it:
  - shadcn registry theme or Tokens Studio export → `WebFetch`/`Read` the JSON,
    map its groups into DTCG `color`/`typography`/`spacing`/`radius`.
  - `tailwind.config` → `Read` it; map `theme.colors`/`fontFamily`/`spacing`/
    `borderRadius`/`boxShadow` into DTCG groups.
  Present the imported set as a **pre-fill** the interview then refines — the
  user confirms/tweaks rather than authoring from zero.
  On fetch/parse failure: fall back to `dtcg_authored`, tell the user, add a
  `WRN-NNN`.
- **`dtcg_authored`** → hand-author each group from the aesthetic + brand.

## Step 2 — theme_modes

Capture which modes the set must resolve under (`light`, `dark`,
`high_contrast`, or others). When >1 mode, encode per-mode colour values — pick
one convention and keep it consistent (e.g. a `$extensions.modes` map per token,
or sibling `color.light.*` / `color.dark.*` groups). Note the convention in a
comment so the downstream agent knows how to read it. `high_contrast` should
pair with the accessibility target (Step 5).

## Step 3 — per-group draft-approve

Run each group as a `high` mini-section (draft → approve/iterate, cap 3).
`color`, `typography`, `spacing` are **required for `status: complete`**;
`radius`, `elevation`, `motion` are recommended but optional.

| Group | Draft from | Notes |
|---|---|---|
| `color` | import + `palette_intent` + `brand_palette` + UX.theming_tokens.colors | Ramps (50–950) for primaries, semantic aliases (primary/danger/success/muted), per-mode values. Brand colours locked (Step 4). |
| `typography` | `typographic_voice` + import | Font families, a modular type scale, weights, line-heights, letter-spacing. |
| `spacing` | `4px`/`8px` base or import | A single base ramp; don't invent per-component spacing. |
| `radius` | aesthetic | Sharp (0) reads brutalist/pixel; large reads friendly. Match `style_family`. |
| `elevation` | aesthetic | Flat looks → few/none; material/glass → graded set. |
| `motion` | `motion_character` | Durations (120–300ms unless expressive) + easings. Should agree with Axis B. |

Don't over-ask: propose a complete, sensible group and let the user trim. A
concrete drafted palette beats ten questions.

## Step 4 — brand palette is locked

If `brand_identity.brand_palette` exists, those colours go into `color`
**verbatim** as named brand tokens — never regenerated or "improved". Build the
rest of the palette (neutrals, semantics) *around* them. Note locked tokens in a
comment.

## Step 5 — contrast against the accessibility target

Honour `UX.accessibility.wcag_target` (and any PRD contrast NFR):

- AA → text/background pairs ≥ 4.5:1 (3:1 large); AAA → 7:1 (4.5:1 large).
- Check the primary text-on-surface and semantic-on-surface pairs you drafted.
  If a pair fails, adjust the value (darken/lighten the ramp step) before
  approving, and record what you did in `contrast_notes`.
- If the user locks a brand colour that fails contrast as text, keep it for
  non-text/accent use, pick an accessible nearby step for text, and note it.

`contrast_notes` is the record that the palette actually meets the target — fill
it whenever an accessibility target exists; it's how the design *traces* the
accessibility NFR (add that NFR id to DESIGN.yaml `implements_requirements`).

## Required for complete

`token_source`, `theme_modes`, `color`, `typography`, `spacing` must be filled
for `DESIGN__tokens.yaml` `status: complete`. Set
`DESIGN.yaml.sub_artifacts.tokens: docs/DESIGN__tokens.yaml` when you write it.
