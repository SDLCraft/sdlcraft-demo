# Asset pipeline — inventory + generation briefs

Read this before **theme 4 (`asset_manifest`)** and **theme 5
(`asset_generation_briefs`)**. Both run only when `asset_pipeline` ∈
`functional_structure` OR `aesthetic_direction.requires_custom_assets` (the
bridge — see `aesthetic-direction.md`). Output: `docs/DESIGN__assets.yaml`.

The manifest is a **requirements** document, not a bag of binaries. The skill
specifies WHICH assets must exist (theme 4) and, for each one that has to be
generated, a ready-to-run PROMPT (theme 5). It never produces binary assets —
that is a downstream / out-of-band step. The brief makes the requirement
actionable *today*.

---

## Theme 4 — the asset inventory (critical synthesis)

A `critical synthesis: true` per-item flow, exactly like UX's surface inventory.
Drive a per-asset state machine, then a scope-completeness sweep before closing.

### Step 1 — seed candidates from every signal

Don't seed only from the taxonomy the user picked. The gap that bites is "the
inventory was drawn from the obvious sprites but missed the UI sounds / the font
/ the entity-implied character." Seed from ALL of:

1. **`asset_taxonomy`** (theme-4 entry question) — each chosen kind implies ≥1
   concrete asset.
2. **PRD `data_model.key_entities` (ENT-###)** — an entity whose description
   names a visible actor/object implies an asset: a `Character`/`Enemy`/`Hero`
   entity → a character sprite; a `Level`/`Map` → a tileset + background; an
   `Item`/`Weapon` → an icon/sprite. Put the ENT-### id in the asset's
   `references_entities`.
3. **UX `surface_inventory` (SCR-###)** — a `canvas`/`overlay`/`page` surface
   implies a backdrop or hero illustration; an `empty_state` surface on a
   hand-drawn UI implies a doodle. Put the SCR-### id in `traces_ux_surfaces`.
4. **Product-type heuristics** — a 2D game almost always needs: player +
   enemy sprites, a tileset, ≥1 background, UI sfx (click/confirm/error),
   ambient/music track, a display font. A hand-drawn token UI almost always
   needs: an icon set, empty-state illustrations, a texture/paper background, a
   logo mark. Cite the heuristic when proposing.

Aim for a starter inventory that covers every chosen taxonomy kind with ≥1
concrete asset.

### Step 2 — per-asset state machine

`AST-NNN` is assigned **at the moment of acceptance** (step a), like UX's
SCR-NNN. Persist `state.last_ids.AST` on each acceptance.

#### a) Propose
```
header: "Asset N"
question: "Asset #N — confirm or revise?"
options:
  - { label: "⚠ <name> (<asset_type>)", description: "⚠ <one-line description>. Seeded from <taxonomy | ENT-### | SCR-### | product-type>. Confirm or correct in the text field." }
  - { label: "Change type / name",       description: "Type a different asset_type or name." }
  - { label: "Set source",               description: "to_be_generated | user_supplied | placeholder (default: to_be_generated for bespoke art)." }
  - { label: "Drop this candidate",      description: "Remove it — no asset created. No AST-NNN consumed." }
```
On accept → assign next `AST-NNN`, record `{ id, asset_type, name, description,
format_hint, source, traces_ux_surfaces (if SCR-seeded), references_entities (if
ENT-seeded), generation_brief: null }`. Persist state.
On drop → record in `state.dropped_asset_candidates`; no id consumed.

#### b) Source semantics
- **`to_be_generated`** — must end with a `generation_brief` (theme 5) or a WRN
  deferral. The default for bespoke art the project doesn't have yet.
- **`user_supplied`** — the user will provide the binary; no brief needed.
- **`placeholder`** — a stub to unblock layout; no brief needed (note it in
  `description`).

#### c) Next or end
```
header: "More?"
question: "Add another asset, or run the scope sweep?"
options:
  - { label: "Add another (I'll suggest)", description: "I'll propose the next candidate." }
  - { label: "Add my own",                  description: "Type a name + type." }
  - { label: "Done — run the sweep",        description: "Reflect over the taxonomy + PRD entities + product type before closing." }
```
**Caps**: soft 15 assets, hard 30. The sweep may push past the soft cap.

### Step 3 — scope-completeness sweep

Before closing, take a reflective pass (the gate that catches forgotten assets).
**Dynamic and project-specific — no canned checklist.** Reflect over:

1. **The draft inventory** — what kinds dominate? What's conspicuously absent
   (sprites but no sfx? characters but no font?)?
2. **Every upstream family** — taxonomy kinds with zero assets; ENT-### actors
   with no sprite; SCR-### surfaces with no backdrop; an accessibility/audio NFR
   implying captions/alt assets.
3. **Project type** — the "obvious once mentioned" set for this product (a game
   needs UI sfx + music + font; a hand-drawn app needs an icon set + logo).

Surface **concrete candidate assets** (not categories) via one `AskUserQuestion`
(multiSelect), 2–4 candidates, with a one-line "why it belongs" each, citing the
signal:
```
- { label: "⚠ ui-click-sfx (audio_sfx)", description: "⚠ You have sprites + music but no UI sounds — every button needs click/confirm/error. Pick to draft." }
- { label: "⚠ enemy-slime-walk (sprite)", description: "⚠ ENT-005 Enemy has no sprite yet. Pick to draft." }
- { label: "Wrap up — inventory complete", description: "Close as-is." }
```
For each picked candidate → re-enter step a (it's the position-1 candidate),
assign the next AST-NNN. Then a second pass.

**Caps**: at most **2 sweep passes**; after two, defer remaining candidates to a
`WRN-NNN` (`"WRN-NNN: asset sweep suggested but not added — <…>"`) and close.
**No sweep** if 0 assets were added (empty inventory is its own signal; write a
`WRN-NNN`). **Anti-padding**: surface 0 candidates rather than manufacture.

### State-write timing (theme 4)

Write state after each step-a/c acceptance, each completed sweep pass, and the
"Done — run the sweep" transition. On EXIT mid-flow: persist accepted assets,
drop the current unconfirmed one (no id consumed), `status: aborted`.

---

## Theme 5 — generation briefs (per to_be_generated asset)

Runs once per asset with `source == to_be_generated`, in id order. Like UX's
per-surface deep-dive: announce the asset, then author its brief. This is the
design analogue of FR-101's `asset_brief_writer` — folded in as a phase, not a
separate agent.

### a) Announce
> "Now: `AST-003` / `hero-knight-idle` (character). Authoring its generation
> brief — modality, tools, prompt, anchors, constraints, acceptance."

### b) Derive modality + tools

`target_modality` from `asset_type`:

| asset_type | target_modality |
|---|---|
| sprite, tileset, background, character, ui_skin, icon, illustration, texture | `image` |
| audio_sfx, audio_music | `audio` |
| model_3d | `model_3d` |
| font | `font` |
| shader | `shader` |
| vfx | `vfx` |
| animation | `animation` (or `image` for a frame sheet) |

`recommended_tools` (advisory, NOT endorsements) by modality:

| modality | typical generators |
|---|---|
| image | SDXL / Flux / Midjourney; pixel art via Aseprite + a pixel LoRA |
| audio | ElevenLabs / Suno / Stable Audio (music); ElevenLabs SFX (sfx) |
| model_3d | Meshy / TripoSR / Rodin |
| font | (usually hand-designed; Fontjoy/Calligrapher for exploration) |
| shader / vfx | engine-native (GLSL) + reference images |

### c) Author the prompt (the core deliverable — `critical`)

Draft a **concrete, ready-to-run** prompt from: the asset `description` + the
`style_anchors` (pulled automatically from `aesthetic_direction.mood_keywords /
palette_intent / style_references / texture_and_finish` + `brand_identity`) +
`assets.style_guide`. Run a draft-approve loop (cap 3). The prompt must be
specific enough that a generator produces a usable, on-style asset without
further context.

- `negative_prompt` — image modalities only; what to exclude (e.g.
  "anti-aliasing, gradients, photorealism" for pixel art). Null otherwise.
- `style_anchors` — confirm/trim the auto-pulled anchors so every brief inherits
  ONE coherent look (this is what keeps the whole asset set consistent).
- `technical_constraints` — from `format_hint` + `render_pipeline` (dimensions,
  format, transparency, duration, sample-rate, poly-budget, texture size).
- `acceptance_criteria` — concrete pass/fail checks a human/agent can verify
  ("readable at 1x", "palette ⊆ shared set", "loops seamlessly", "< 5k tris").
- `variation_notes` — optional seed/batch/variation guidance.

### Coverage — trace OR defer (the gate)

Every `to_be_generated` asset must end with EITHER a non-null `generation_brief`
OR a `WRN-NNN` deferral in `DESIGN.yaml.design_warnings` that **names its
AST-NNN** (e.g. `"WRN-005: AST-007 deferred — final boss art pending art
direction"`). The validator enforces this deterministically (errors in
`complete`, warnings in `draft`) and counts a deferred asset as covered. This is
the FR-101 coverage assertion: it's deterministic, which is exactly why the
*prompt* is gated but binary asset *quality* is not (that stays out of band).

`user_supplied` / `placeholder` assets need no brief and are never flagged.

### State-write timing (theme 5)

Persist after each approved brief (flip `defined_assets[i].has_brief = true`).
On EXIT mid-brief: keep approved briefs; the in-progress one stays unbriefed
(it'll be flagged by coverage as draft) — `status: aborted`. On resume, continue
at the first `to_be_generated` asset whose `has_brief` is false.
