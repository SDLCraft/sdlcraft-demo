# SDLCraft Demo

Spec-driven development for [Claude Code](https://code.claude.com). Structured
interviews turn an idea into machine-readable specs — requirements, UX, design,
data model, API and architecture — that AI agents can build from. Every spec is
validated, every id is traceable from requirement to architecture, and each
stage tells you exactly what to run next.

This is the **demo edition** (MIT). It takes a project from idea to a complete,
validated architecture. The full edition, SDLCraft, continues from there to
tested code — see [Editions](#editions).

> Pre-1.0 (version 0.9.12): expect the skills to keep changing.

## Install

```
claude plugin marketplace add sdlcraft/sdlcraft-demo
claude plugin install sdlc@sdlcraft-demo
```

The skills' validators need Python 3.10+ with `pydantic>=2` and `pyyaml`:

```
pip install "pydantic>=2" pyyaml
```

## Use

Run the stages in order, each in a fresh session. Every stage ends by naming
the next command.

| Command | Produces |
|---|---|
| `/sdlc:setup` | project wiring — run once |
| `/sdlc:prd` | `docs/PRD.yaml` — requirements |
| `/sdlc:ux` *(optional)* | `docs/UX.yaml` — screens and flows |
| `/sdlc:design` *(optional)* | `docs/DESIGN.yaml` — visual design tokens |
| `/sdlc:data` | `docs/DATA-MODEL.yaml` |
| `/sdlc:api` *(optional)* | `docs/API.yaml` |
| `/sdlc:arch` | `docs/ARCH.yaml` — containers, components, contracts |
| `/sdlc:repair` | fixes a spec defect at the stage that caused it |

## Editions

| | Demo | SDLCraft |
|---|:---:|:---:|
| Requirements → architecture specs | ✓ | ✓ |
| Spec repair | ✓ | ✓ |
| Test strategy (`/sdlc:test`) | | ✓ |
| Dependency-ordered task graph (`/sdlc:task`) | | ✓ |
| Test-first code generation with a self-healing loop (`/sdlc:code`) | | ✓ |

SDLCraft keeps every command and every file you already have — upgrading is
uninstall, install, and one `/sdlc:setup` per project. It is a subscription,
one seat per developer, sold by Polar Software Inc. as merchant of record. The
subscription buys updates: cancel and you keep every version you received, you
just stop getting new ones. Everything the pipeline generates is yours either
way.

It is currently in an invite-only beta — open an issue in this repository to
ask for access.

## Feedback

`/sdlc:setup` asks once whether to share anonymous reports about defects in the
skills themselves; the default is off, and declining costs you nothing. Nothing
about your project's content is sent — see [`PRIVACY.md`](PRIVACY.md) for what
a report does and does not contain. Issues and ideas are welcome in this
repository.

## Legal

MIT — see [`LICENSE`](LICENSE). The MIT licence covers the code, not the name:
SDLCraft is a trade mark of Andreas Pfrengle. Fork it under a different name
and you're welcome to. Privacy: [`PRIVACY.md`](PRIVACY.md).

Andreas Pfrengle (Einzelunternehmer), Am Blasiwald 34, 79183 Waldkirch, Germany · sdlc@agentmail.to
