# Sub-model decomposition + bounded-context reconciliation

Read this on entering the `entities` theme (Phase 6) and again before writing
`status: complete` (Phase 7). It closes the two gaps that most often make a
DATA-MODEL.yaml shallow or invalid:

1. **Under-decomposed entities** — the agent models the top-level entity but
   never breaks its nested structures into their own definitions, so a field
   like `features: list[FeatureSpec]` references a `FeatureSpec` that is never
   actually defined. The model "validates" against a loose schema but tells a
   downstream codegen agent almost nothing.
2. **Unassigned entities** — entities (especially the sub-models from #1) are
   added to the `entities` block but never added to any `bounded_contexts.<fam>.
   entities` list. The validator's bounded-context partition check then fails
   with "entity X is not assigned to any context" — and in manual practice this
   silently piled up (dozens of orphans) because no one ran a reconciliation.

Both are amplified for the **file_native (Pydantic)** and **document** paradigms,
where nested models / embedded sub-documents are the norm — but the discipline
applies to every paradigm.

## Part A — exhaustive sub-model decomposition (per entity)

When detailing each entity in the `entities` theme, do not stop at its
top-level fields. **Walk every field's type and recurse:**

- A field typed as a **scalar** (`str`, `int`, `bool`, `datetime`, `Decimal`,
  …), an **enum** (define it under `enums_and_lookups`), or a **reference to
  another first-class entity** → terminal; nothing to decompose.
- A field typed as a **custom model** — directly (`identity: IdentityAndAuth`),
  in a collection (`features: list[FeatureSpec]`, `slots: dict[str, ShapeCandidate]`),
  or optional (`Optional[CoverageThreshold]`) — names a **sub-model that MUST
  exist as its own `entities.<Name>` entry**. Define it, then recurse into *its*
  fields. Keep going until every leaf is a scalar, an enum, or an entity
  reference.
- A field typed as a **union** of models — `Union[CardPayload, BankPayload]`,
  `CardPayload | BankPayload`, or a prose "one of" — names a **union parent**:
  define it as its own entity with `one_of: [CardPayload, BankPayload]` and
  `discriminator: <field>` (no fields of its own), then define every variant
  as a first-class entity carrying that discriminator field. A union is
  neither a mixin (`composes`) nor containment (`composition`).

For the **file_native** paradigm, promote each such nested model to a
first-class entry with `category: sub_model` and wire the parent→child link in
the top-level `composition` block (`kind: embeds`). For **document**, embedded
sub-documents are modelled the same way (composition `embeds`); id-linked
documents use `cross_references`. For **relational**, a nested structure is
usually either a JSON(B) column (keep inline) or a child table (its own entity
with a FK) — decide per case, but still name it.

**Promotion threshold.** Promote a nested structure to its own entry when it
has **≥2 fields**, is **reused by ≥2 parents**, or is **independently
referenced** downstream. A trivial one-scalar wrapper can stay inline — note it
in the parent's field description rather than manufacturing a noise entry.

**The decomposition is itself a sweep.** After the per-entity loop and the
entity scope-completeness sweep (see `entity-discovery.md`), do a dedicated
**sub-model pass**: re-read every entity's fields and list every type that is
not a scalar/enum/entity-reference. Each one must resolve to a defined entry.
Surface the missing ones to the user the same way the entity sweep does (one
multi-select `AskUserQuestion`, concrete names with their parent + field cited):

```
header: "Sub-models"
question: "These entities reference nested models that aren't defined yet — each
  should be its own sub_model entry so codegen knows its shape. Define which?"
options:
  - { label: "⚠ FeatureSpec",      description: "⚠ Referenced by ProductRequirements.features (list[FeatureSpec]). Pick to define its fields." }
  - { label: "⚠ CoverageThreshold", description: "⚠ Referenced by TestStrategySpec.pyramid_targets. Pick to define." }
  - { label: "Wrap up — all defined", description: "Every referenced model already has an entry." }
multiSelect: true
```

Anti-padding still holds: only surface types that are genuinely referenced and
genuinely missing — don't invent wrappers to look thorough.

## Part B — bounded-context reconciliation (before `status: complete`)

Runs only when bounded contexts are enabled (Phase 4 opt-in). The validator
enforces a **partition**: every entity key appears in exactly one
`bounded_contexts.<family>.entities` list, and every name listed there is a real
entity. Run this reconciliation proactively in Phase 7 so the file passes:

1. Build `defined = set(entities.keys())` and
   `assigned = union(bounded_contexts.<fam>.entities)`.
2. **Orphans** = `defined − assigned` — entities (very often the sub-models from
   Part A) not placed in any context.
3. **Phantoms** = `assigned − defined` — names listed in a context that no longer
   exist (typically renamed/removed entities).
4. **Duplicates** — any entity listed in two contexts.

If all three sets are empty, the partition is complete — proceed. Otherwise
surface them to the user and resolve:

- For each **orphan**, propose the most likely context from the entity's
  `category` (e.g. `category: sub_model` → the `sub_models` family;
  `category: runtime_state` → the runtime context) and let the user confirm or
  re-home. Assigning by category is usually a one-click batch.
- For each **phantom**, ask whether to drop the stale name or restore the entity
  (never silently delete — see the upstream-ID staleness rule).
- For each **duplicate**, ask which single context owns it.

Then re-run steps 1–4 until clean. This is exactly the check
`validate_schema.py` runs (`bounded-context partition`); doing it here means the
validator never reports orphans at write time.

**Why a category default helps:** most orphans are sub-models, and the
`sub_models` family is their natural home — so the common case is "assign all
N orphans to their category-implied context, confirm once." Reserve per-entity
prompting for the ambiguous few.

## EXIT / state

Both passes write state after each accepted batch (same cadence as the entity
sweep). On EXIT mid-pass, record a `WRN-NNN` in `data_warnings`:
`"WRN-NNN: sub-model decomposition incomplete — <Type>, <Type> referenced but
undefined"` or `"WRN-NNN: bounded-context partition incomplete — <Entity>
unassigned"`, so a resumed or downstream pass knows what is left.
