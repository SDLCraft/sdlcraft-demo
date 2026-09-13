# OpenAPI 3.1 embedding — what's in scope, what's not

Read this when entering **theme 10 (`per_resource_deepdive`)** or
**Phase 7 (write & validate)** for any non-`none` API.

`sdlc:api` embeds OpenAPI 3.1 operation objects inside per-resource
yamls (and OpenAPI 3.1 component schemas in both per-resource yamls
and the shared `API.yaml.shared_schemas`). The full OpenAPI spec is
too permissive for downstream coding agents, so the skill works with a
deliberately constrained subset.

## Why a subset

OpenAPI 3.1 has many features aimed at human readers (Markdown
descriptions, examples galleries, server variables, callbacks, links,
discriminators, `xml`). Downstream coding agents don't need any of
these; they add ambiguity and complicate validation. The subset below
keeps everything a code generator needs and drops the rest.

## Supported OpenAPI 3.1 keywords

### Per-endpoint (inside an entry in `endpoints[]`)

Required for `status: complete`:

- `id` — SDLC sibling. Stable `OPR-NNN` (zero-padded 3-digit) used as
  the cross-stage reference contract by downstream test/task/arch
  agents. Assigned by the writer in collection order; persisted via
  `state.last_ids.OPR`. Stripped before any OpenAPI tool round-trip.
- `operation_id` — kebab or snake-case unique id used by downstream
  codegen for function names. Editable; `OPR-NNN` is the stable
  contract.
- `method` — `GET | POST | PUT | PATCH | DELETE | HEAD | OPTIONS`.
- `path` — full HTTP path; usually starts with the resource's
  `base_path`. Surface deviations as a warning during deep-dive.
- `summary` — one-line description.
- `responses` — at least one entry; each entry is an OpenAPI response
  object with `description` + `content` (when a body is returned).

Optional:

- `description` — longer description (one paragraph max — terser is
  better for AI consumers).
- `tags` — list of strings.
- `parameters` — list of OpenAPI parameter objects; `in` ∈ `path |
  query | header` only (cookie parameters are out of scope).
- `requestBody` — OpenAPI requestBody object.
- `security` — list of OpenAPI security requirement objects; names
  match `API.yaml.auth.schemes` entries.

SDLC siblings (alongside the OpenAPI keys; stripped before any
OpenAPI tool round-trip):

- `id` — see Required block above. Stable `OPR-NNN` reference.
- `idempotent` — `true | false | null`; `null` means "inherit
  `API.yaml.idempotency.idempotent_methods`".
- `rate_limit_override` — string; `null` means "inherit
  `API.yaml.rate_limiting`".
- `auth_override` — string; `null` means "inherit
  `API.yaml.auth.default_visibility`".

### Per-schema (inside `schemas:` or `shared_schemas:`)

Required:

- `type` — usually `object`; primitives (`string`, `integer`, …) for
  scalar aliases.
- `properties` — for `type: object`. Each property is a JSON Schema
  2020-12 subset.
- `projects_from` — SDLC sibling. **Required** for object DTOs: the
  DATA entity name this DTO projects from (must exist in
  `DATA-MODEL.entities`). Set to `null` only for genuine cross-entity
  wrappers — paginated list envelopes, search responses, RFC-7807
  Problem, aggregated dashboard payloads. Downstream agents wire
  ORM↔DTO mappers off this field; a missing `projects_from` on a
  single-entity DTO is a soft fail (validator warns).

Recommended:

- `required` — list of property names that are non-null.
- `description` — one-line, optional.

### Per-property (a JSON Schema 2020-12 subset)

In scope:

- `type` — `string | integer | number | boolean | array | object | null`.
- `format` — common formats only: `uuid | date | date-time | email |
  uri | ipv4 | ipv6 | hostname | byte | binary | int32 | int64 |
  float | double`.
- `enum` — list of allowed values.
- `default` — used by downstream codegen; only meaningful for
  optional properties.
- `nullable` — boolean. (OpenAPI 3.1 uses `type: [..., 'null']`; the
  shorthand `nullable: true` is also accepted and rewritten on
  round-trip.)
- `minLength`, `maxLength`, `pattern` — for `type: string`.
- `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`,
  `multipleOf` — for numeric types.
- `minItems`, `maxItems`, `uniqueItems` — for arrays.
- `items` — required for arrays.
- `$ref` — references; see below.

Out of scope (do NOT use):

- `xml`, `externalDocs`, `discriminator`, `callbacks`, `links`,
  `servers`, `securitySchemes` at the operation level, `example`,
  `examples`. Use `description` for any human-readable hint a
  downstream agent might benefit from.
- `oneOf` / `anyOf` / `allOf` — out for v1 because they complicate
  codegen for DTOs. Polymorphism is a v2 problem.
- `not` — out.

## `$ref` syntax — three flavours

### 1. Within the same file

Standard OpenAPI:

```yaml
schemas:
  User:
    type: object
    properties:
      address:
        $ref: "#/components/schemas/Address"
  Address:
    type: object
    ...
```

`#/components/schemas/<Name>` is supported (the validator rewrites
this to `#/schemas/<Name>` on read — we don't use the OpenAPI
`components` wrapper since `schemas:` is at the top level of the
resource yaml).

### 2. To `API.yaml.shared_schemas` (cross-file)

For schemas shared across ≥2 resources (e.g. `Money`, `Pagination`,
RFC-7807 `Problem`):

```yaml
schemas:
  User:
    type: object
    properties:
      balance:
        $ref: "../API.yaml#/shared_schemas/Money"
```

The relative path `../API.yaml` works because `docs/API.yaml` and
`docs/API__<resource>.yaml` are siblings.

### 3. To `DATA-MODEL.yaml` entities (cross-skill)

DTOs may reference DATA entities directly using a custom scheme that
downstream agents resolve at codegen time:

```yaml
schemas:
  User:
    projects_from: User
    type: object
    properties:
      profile:
        $ref: "data-model://Profile"
```

`data-model://<EntityName>` is the SDLC convention. The validator
checks that `<EntityName>` exists in `DATA-MODEL.entities` as part of
the entity-link check. Downstream agents resolve this to the
appropriate ORM type (TypeORM, Prisma, SQLAlchemy, …) when
generating code.

## DTO-vs-entity discipline (the most important rule)

Schemas in API__<resource>.yaml (and in `API.yaml.shared_schemas`)
are **wire DTOs**, NOT persistent entities. The line:

- **Persistent entity** = a row in storage (ORM model, database
  schema, document store). Defined in `docs/DATA-MODEL.yaml`.
  Includes fields like `password_hash`, `internal_flags`,
  `deleted_at`, server-only metadata.
- **DTO (Data Transfer Object)** = the shape sent over the wire to a
  client. May omit persistence-only fields, rename for client
  ergonomics, add computed fields. Defined in this skill.

### What to omit — anchored in DATA-MODEL

`DATA-MODEL.yaml.data_classification` is the **authoritative source**
for "what must not leak through public DTOs". When drafting a DTO for
entity `<E>`, omit by default any field referenced as `<E>.<field>` in:

- `data_classification.regulated_fields` — PHI / PCI / other regulated
  data. Never expose in a public DTO; exposing requires a *named
  admin-only DTO* (e.g. `UserAdmin`) with the user's explicit override
  per resource.
- `data_classification.localized_fields` — user-visible text stored once
  per locale. Expose it, but as the single locale negotiated via
  `Accept-Language` (never the whole locale map) — pairs with
  `errors.localisation`.
- `data_classification.encrypted_at_rest` — column-encrypted. Same
  default-omit rule (the wire value would either be ciphertext or a
  fresh decrypt the server shouldn't reveal lightly).
- `data_classification.pii_fields` — case-by-case: PII like `email` is
  usually present in the owner's own DTO but omitted from
  `<E>Public` / cross-tenant DTOs. The agent must surface each PII
  field per resource and let the user pick.

Always omit (DATA convention, not in `data_classification`):

- Password / token / secret hashes (`*_hash`, `*_secret`, `password_*`).
- Soft-delete sentinels (`deleted_at`, `is_deleted`) — filter at the
  read layer, never surface.
- Server-only timestamps the client doesn't need (`indexed_at`,
  `last_synced_at`).

### Soft-delete and DELETE semantics

If `DATA-MODEL.audit_and_lifecycle.soft_delete: true`, the
`delete-<resource>` endpoint is **soft-delete**: returns `204 No
Content`, sets `deleted_at` server-side, and subsequent reads filter
the row out. The DTO does NOT include `deleted_at`. If
`soft_delete: false` (or unset), DELETE is a hard-delete — the row is
gone, subsequent reads return `404`.

Tell the user during theme 10 which mode the resource will run in so
the choice ends up traceable.

### Identifier formats — driven by `id_strategy.scheme`

The path parameter `{id}` and DTO `id` field format follow
`DATA-MODEL.id_strategy.scheme`:

| `id_strategy.scheme` | DTO `id` | Path-param `format` |
|---|---|---|
| `uuid_v4`, `uuid_v7` | `type: string, format: uuid` | `format: uuid` |
| `ulid` | `type: string, format: ulid` (custom) | `pattern: "^[0-9A-HJKMNP-TV-Z]{26}$"` |
| `nanoid` | `type: string` | `pattern: "^[A-Za-z0-9_-]{10,21}$"` |
| `serial_int`, `bigserial` | `type: integer, format: int64` | `format: int64` |
| `natural_key` | `type: string` | application-specific |
| `mixed` | follow per-entity `primary_key` field type | follow per-entity |

For composite primary keys (`primary_key: [tenant_id, slug]`), the
path takes both segments: `/v1/tenants/{tenant_id}/items/{slug}`.

### Enum DTO fields — pulled from `enums_and_lookups`

If a DTO field maps to a DATA field of `type: enum` or to a
`lookup_tables` entry, embed the enum values directly:

```yaml
schemas:
  Order:
    projects_from: Order
    properties:
      status:
        type: string
        enum: [pending, paid, shipped, refunded]  # from DATA.enums_and_lookups.enums.OrderStatus
```

Downstream codegen needs the enum inline because enums in the OpenAPI
output drive client-side types.

### DTO projections — recommended starter set

For each entity `<E>` with no overrides:

- `<E>` — the canonical read DTO (omit per `data_classification`).
- `<E>Create` — the POST body (omit server-set fields: `id`,
  `created_at`, `updated_at`, any `default: now()` field).
- `<E>Update` — the PATCH body (all properties optional; PUT is rare
  but if present requires the same fields as Create).
- `<E>Admin` (optional) — privileged read DTO that re-exposes
  regulated / sensitive fields; gated behind an admin scope.
- `<E>Public` (optional) — cross-tenant read DTO that further hides
  PII (e.g. exposes only `id`, `display_name`).

When in doubt: ask the user during theme 10. The default-omit rule
above is conservative — re-adding a field is a one-line override; a
leaked field is a security incident.

## OpenAPI deep-validation is out of scope for v1

`validate_schema.py` validates the SDLC shape of each endpoint
(required keys, methods, etc.) but does NOT call out to an OpenAPI
validator like `openapi-spec-validator`. Reasons:

1. The SDLC-specific siblings (`idempotent`, `rate_limit_override`,
   `auth_override`, `projects_from`) and the custom `$ref` forms
   above would be flagged as invalid by a strict OpenAPI validator
   without preprocessing.
2. Downstream coding agents will typically synthesize a fresh
   OpenAPI document from the SDLC artifacts and validate that — full
   round-trip parity isn't useful here.
3. Pinning an `openapi-spec-validator` version drags in a sizeable
   transitive dependency tree.

This is a deliberate v1 trade-off. A future version may add
preprocessing + opt-in deep validation.

## Mapping back to a vanilla OpenAPI document (downstream-agent
recipe)

For agents that want a strict OpenAPI 3.1 document for codegen tooling:

1. Start with a fresh document:
   ```yaml
   openapi: 3.1.0
   info:
     title: <PRD.product_identity.name>
     version: <API.yaml.versioning.current_version>
   paths: {}
   components:
     schemas: {}
   ```
2. For each resource in `API.yaml.resource_inventory`, load its
   `API__<resource>.yaml`:
   - For each endpoint, write to `paths[<path>][<method>]` as a vanilla
     OpenAPI operation. **Strip** the SDLC siblings (`id`/OPR-NNN,
     `idempotent`, `rate_limit_override`, `auth_override`). Optionally
     preserve the OPR-NNN id as an `x-opr-id` extension if downstream
     consumers want it.
   - For each schema in the resource's `schemas`, write to
     `components.schemas[<name>]`. **Strip** the SDLC sibling
     `projects_from`.
3. For each entry in `API.yaml.shared_schemas`, write to
   `components.schemas[<name>]` as well. **Resolve cross-file `$ref`**
   from `../API.yaml#/shared_schemas/<Name>` to
   `#/components/schemas/<Name>`.
4. **Resolve `data-model://<EntityName>` `$ref`s**: substitute the
   DATA entity's shape (from `docs/DATA-MODEL.yaml.entities[<Name>]`)
   under `components.schemas[<EntityName>]` and rewrite the `$ref` to
   `#/components/schemas/<EntityName>`.

This is a deterministic transform — every downstream agent should
produce the same OpenAPI document from the same SDLC artifacts.
