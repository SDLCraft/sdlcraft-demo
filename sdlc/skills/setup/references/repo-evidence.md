# Repo evidence — folding what already exists into the pre-fill map

Every skill after `prd` used to read `docs/` and nothing else. On a greenfield
project that is right. On a **brownfield** one it throws away the best evidence
in the room: the migrations, route files, Dockerfiles, token files and test
layout already on disk.

`setup` installs `.claude/sdlc/repo_scan.py` for exactly this. Each skill asks
for its own domain in **Phase 3**, while it is building the pre-fill map:

```bash
python .claude/sdlc/repo_scan.py --domain <skill> --json
```

Absent helper (the project never ran `/sdlc:setup`) → skip silently and build
the pre-fill map from upstream artifacts alone. Never block a run on it.

## The four rules

1. **Evidence is a candidate, never an answer.** Every hit enters the pre-fill
   map tagged **`⚠ inferred`**, which the canonical flow already forbids
   batch-accepting — each one needs its own confirmation. Present it as *"the
   repo has X — is that still what you want?"*, never as a filled field.

2. **Cite the file and line.** Put `<path>:<line>` in the `_rationale` sibling
   of whatever field the evidence fed, the same way `prd` quotes
   `[from package.json]`. A pre-fill the user cannot trace back is a pre-fill
   they cannot check.

3. **What exists is not what is wanted.** This matters most for `arch`: the
   current module layout is the structure the project *has*, and the interview
   exists to decide the structure it *should* have. Seed the candidate list
   with it; never let it silently become the answer. Same for `data` — an
   existing table is evidence of an entity, not proof its current shape is
   right.

4. **Say when the sweep was partial.** The helper caps how much it reads and
   returns `truncated: true` when the repo is bigger than that. Pass that on:
   *"this is a sample of a large repo, not an inventory."* Same for
   `capped_signals`.

## Contradiction with an upstream artifact

When the repo says one thing and an upstream artifact says another — the PRD
says PostgreSQL, the repo has `schema.prisma` pointing at SQLite — **surface
the conflict, do not resolve it**. One `AskUserQuestion` naming both sources
and where each came from. The upstream artifact is the specification and the
repo is the current state; which one is stale is the user's call, and getting
it wrong silently is worse than asking.

If the answer is "the artifact is wrong", that is a `FND-NNN` finding for
`/sdlc:repair` (CLAUDE.md §13) — not something this skill patches upstream.

## What each domain returns

| domain | signals |
|---|---|
| `prd` | readme, manifests, idea/vision/pitch docs, monorepo `workspaces` |
| `ux` | CLI arg parsers (python/js/rust), route dirs, templates, component dirs, i18n catalogs |
| `design` | tailwind config, token files, CSS custom properties, component library, fonts, asset dirs |
| `data` | migrations, `schema.prisma`, `CREATE TABLE` SQL, ORM/pydantic models, TS interfaces, DB services in compose |
| `api` | OpenAPI/Swagger, `.proto`, GraphQL SDL, route decorators, `urls.py` |
| `arch` | package manifests, Dockerfiles, compose, terraform, k8s/helm, CI workflows, Procfile |
| `test` | test dirs, pytest/jest/vitest/playwright config, coverage config, fixtures/factories, CI test jobs |
| `task` | Makefile/Taskfile/justfile, npm scripts, lint + format config, pre-commit |

`python .claude/sdlc/repo_scan.py --list` prints this from the installed copy,
which is authoritative if the two ever disagree.
