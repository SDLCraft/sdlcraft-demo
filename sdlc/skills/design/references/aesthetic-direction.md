# Aesthetic direction — running Axis B

Read this before **theme 2 (`aesthetic_direction`)**. Axis B is WHAT the product
looks and feels like. It is the creative heart of the skill and the part a blank
form handles worst — so the agent always **drafts a direction first**, then lets
the user steer.

## The open vocabulary

`style_family` is a **free-form string**, not a closed enum. The curated anchors
(`minimal_flat`, `material`, `skeuomorphic`, `neumorphic`, `glassmorphic`,
`claymorphic`, `brutalist`, `corporate_brand`, `editorial`, `retro_terminal`,
`pixel_art`, `vaporwave`, `hand_drawn`, `comic_ink`, `manga`, `pop_art`,
`painterly`, `data_ink`) are recommendation anchors and an AI starting point —
**never a cap**. If the user coins a style ("Bauhaus-meets-cyberpunk"), store it
verbatim. The free-form fields (`mood_keywords`, `palette_intent`,
`texture_and_finish`) carry whatever the anchor set can't name.

## Drafting the direction from PRD + UX

Before asking anything, compose a 2–4-sentence draft direction from:

- **PRD** `product_identity` (name, one_liner, idea_text → the product's
  personality), `users_personas` (audience → formality/energy),
  `non_functional_requirements` (accessibility/brand NFRs → constraints).
- **UX** `design_principles.tenets` + `inspiration_refs` (the interaction
  references — note these are UX products like Linear/Notion, *adjacent to* but
  not the same as visual style references), `content_rules.tone` (→
  typographic/brand voice), `component_library` (a library hints at a default
  look that the aesthetic can keep or override).

Lead theme 2 with that draft ("Given your calm, trustworthy PRD and the Linear
reference in UX, I'm proposing a minimal-flat direction with cool neutrals and
one warm accent…") and run the `high` draft-approve loop (propose → approve or
iterate, cap 3) for `style_family` + `mood_keywords`, then batch the remaining
`med` fields.

## Grounding with `style_references` (web_fetch)

`style_references` are URLs / named works / artists / art movements that capture
the look. When the user supplies a URL, **fetch it** (WebFetch) and summarize
its visual language — dominant palette, type treatment, spacing density,
texture, motion — then fold that into `palette_intent` / `typographic_voice` /
`texture_and_finish`. Rules:

- **Never invent URLs.** Only fetch what the user gives or explicitly confirms.
- Named works/artists/movements that aren't URLs are stored as-is (they're
  anchors for a downstream agent), no fetch needed.
- On fetch failure: proceed from the user's words and add a `WRN-NNN` note.

## The bridge: artistic look → `requires_custom_assets`

This is the most important inference in the skill. A component library ships
*generic* assets (icons, default illustrations). An **artistic** look cannot be
realized with those — it needs bespoke illustration, custom icon sets, textures,
hand-drawn empty-states. So:

**Pre-answer `requires_custom_assets: true`, then confirm, when EITHER:**

- `style_family` is an artistic family — `hand_drawn`, `comic_ink`, `manga`,
  `pop_art`, `painterly`, `pixel_art`, `vaporwave`, `claymorphic`,
  `skeuomorphic` (anything that implies drawn/painted/sculpted surfaces); OR
- `texture_and_finish` is non-trivial — rough ink borders, paper grain,
  halftone, cel-shading, hand-painted textures.

Otherwise pre-answer `false` (a plain library-default look on a token UI needs
no bespoke assets).

When it fires on a `token_based_ui` that didn't already select `asset_pipeline`,
say so and turn the manifest on:

> "A hand-drawn look on a component UI means the icons, illustrations, and
> empty-state art have to be bespoke — a stock icon set would break the style.
> I'll turn on an asset manifest (`requires_custom_assets: true`) so those get
> specified. Sound right?"

This is what makes "token UI + comic style" actually buildable. It is the design
analogue of the UX scope-completeness sweep — **skip it at your peril**: a
gorgeous aesthetic with no asset manifest leaves a downstream agent reaching for
generic clip-art that wrecks the look.

Confirm rather than force: if the user insists an artistic look needs no custom
assets (e.g. they'll buy an asset pack), respect it, set `false`, and add a
`WRN-NNN` noting the look depends on externally-sourced assets.

## Motion + accessibility

`motion_character` (`none|subtle|expressive|playful`) should agree with the
motion tokens later. Regardless of the value, `prefers-reduced-motion` is
honoured if UX.accessibility flagged it — note that in `texture_and_finish` or a
token `motion` comment so the downstream agent gates animations.

## Headless families on Axis B

- **`service` / `library`** — Axis B is normally null. Don't manufacture a look.
- **`cli`** — optional light aesthetic: a terminal colour scheme
  (`style_family: retro_terminal` or `data_ink`), output density, ASCII/spinner
  character. Capture in `aesthetic_direction`; no tokens/assets.
- **`voice`** — there are no visuals, but persona is real: capture voice/persona
  in `mood_keywords` + `typographic_voice` (reused as "spoken voice") and, if
  branded, `brand_identity.brand_voice`. No tokens/assets.

## Confidence

`style_family` and `requires_custom_assets` carry `_confidence`:
`confirmed` (user picked/typed) or `inferred` (`⚠` accepted as-is). A look the
agent proposed and the user accepted unchanged is `inferred`; one the user
shaped via free text is `confirmed`.
