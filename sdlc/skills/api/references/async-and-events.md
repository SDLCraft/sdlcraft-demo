# Async and events — when to populate the `events` block

Read this when entering **theme 9 (`events_async`)**.

The `events` block in `API.yaml` describes everything that isn't a
plain request-response REST/GraphQL/gRPC call: server-pushed events,
client-sent messages over a persistent connection, and outbound
webhooks the server fires when state changes. The block is populated
only when `transport_styles` includes one of `websocket`,
`server_sent_events`, or `webhooks_out`.

## When the theme is required

`events_async` is marked `required_if: transport_styles includes
websocket | server_sent_events | webhooks_out`. The agent re-evaluates
this at the start of each theme batch. If the user adds `webhooks_out`
to `transport_styles` mid-interview (during a Phase 5 pre-fill
correction, say), the theme gets promoted on the next batch boundary.

If the user picks a transport style here but no UX surface or PRD
feature suggests an event-y workflow, ask one clarifying
`AskUserQuestion`:

```
header: "Confirm?"
question: "You chose `<transport>` but none of the UX surfaces or PRD features mention real-time updates. Do you still want an event channel?"
options:
  - { label: "Yes — type the use case",  description: "Use the text field to describe the trigger (e.g. 'admin live dashboard')." }
  - { label: "No — drop <transport> from transport_styles", description: "Remove and proceed without the events theme." }
```

## What goes in `events.channels[]`

Each channel is one event topic. Each entry has:

- `channel_id` — kebab-case unique id (e.g. `task-created`,
  `user-typing`, `payment-completed`).
- `transport` — one of:
  - `websocket` — bidirectional, persistent.
  - `sse` — server-to-client, persistent, one-way.
  - `webhook` — server-to-server, outbound HTTP POSTs.
  - `queue` — internal queue (Kafka, SQS, …); not exposed to clients
    directly. Use sparingly — usually queue contracts belong in
    `docs/ARCH.yaml`, not API.yaml.
- `direction` — one of:
  - `server_to_client` — server pushes (SSE, server WebSocket frames).
  - `client_to_server` — client publishes (WebSocket frames).
  - `outbound_webhook` — server POSTs to a customer URL.
  - `both` — bidirectional WebSocket only.
- `payload_schema_ref` — `$ref` into `API.yaml.shared_schemas` or a
  per-resource schema. The payload schema is just a regular
  OpenAPI 3.1 component schema; see `references/openapi-embedding.md`.
- `auth_ref` — which auth scheme applies. For WebSocket/SSE this is
  usually the same bearer token as REST. For outbound webhooks it's
  typically a per-channel HMAC secret.

## Payload conventions

The agent proposes one of three patterns by default:

### 1. JSON envelope (recommended)

```json
{
  "type": "task.created",
  "id": "evt_abc123",
  "timestamp": "2026-05-18T12:00:00Z",
  "data": { /* the resource payload */ }
}
```

`type` is a string discriminator (e.g. `task.created`,
`task.updated`, `user.deleted`). Consumers switch on `type` to route.

This is the easiest pattern for SDK codegen and the most common in
the wild. Use unless the user has a strong reason otherwise.

### 2. CloudEvents 1.0

If the product needs interop with cloud-native eventing
(Knative, Kafka with CloudEvents headers, AWS EventBridge), use the
[CloudEvents 1.0 spec](https://github.com/cloudevents/spec) directly.
The agent shouldn't propose this unless the user mentions
CloudEvents or one of these systems explicitly.

### 3. Plain payload (no envelope)

Just send the resource shape with no wrapper. Simpler but loses
event-id / type info. Recommended only when:

- One channel = one event type (no need for `type` discriminator).
- Server pushes are display-only (typing indicators, cursor
  positions) and dedup/replay isn't a concern.

## Delivery guarantees

| Guarantee | Meaning | When to pick |
|---|---|---|
| `at_most_once` | Server may drop messages; consumers may miss events | Display-only ephemeral data (typing indicators, presence) |
| `at_least_once` | Server retries on failure; consumers must dedupe by event id | Default for state-change webhooks (Stripe-style); requires a stable `event.id` |
| `exactly_once` | Server guarantees no dup, no loss | Rarely truly achievable; only pick if the underlying transport (Kafka with EOS, …) supports it AND the user explicitly asks |

For most products: `at_least_once` is the right default. Be explicit
about consumer dedup in the payload conventions ("consumers must
dedupe by `event.id`").

## Consumer auth — three flavours

- **HMAC signature** (recommended for outbound webhooks). Server signs
  the payload with a per-channel secret; consumer verifies via
  `X-Signature: t=<ts>,v1=<hex>` header. Stripe-style. The secret is
  shown to the customer once at channel creation and never again.
- **Same bearer JWT as REST** (recommended for WebSocket/SSE). The
  client connects with the same auth token used for REST calls; the
  connection is per-user and the server enforces the same role/scope
  checks.
- **Per-channel webhook secret** (legacy). Shared static secret —
  simpler than HMAC but weaker. Don't recommend for new APIs.

## What does NOT go in `events`

- **Internal queue contracts** (job queues, work distribution between
  services). Those belong in `docs/ARCH.yaml`, not the public API
  surface.
- **Database CDC / replication streams**. Same — internal architecture.
- **In-app notifications** (the toast popping up when a task is
  completed) — that's a UX surface, not an event channel. The data it
  consumes likely *does* come from an event channel here; the UI is
  separate.

When in doubt, ask: "Is a third party going to consume this event?" If
yes → API.yaml. If no → ARCH.yaml.

## AsyncAPI alignment

The `events` block is loosely aligned with [AsyncAPI 3.0](https://www.asyncapi.com/)
but does NOT embed AsyncAPI documents directly in v1. Reasons:

- AsyncAPI tooling is less mature than OpenAPI tooling for codegen.
- Most coding agents handle WebSocket/SSE/webhook code from custom
  prompts more reliably than from an AsyncAPI spec.

If the user explicitly needs a full AsyncAPI document, downstream
agents can synthesize one from the `events` block + the referenced
payload schemas, similar to the OpenAPI synthesis recipe in
`references/openapi-embedding.md`. v2 may add native AsyncAPI embed.
