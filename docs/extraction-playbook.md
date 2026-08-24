# Extraction playbook: what it actually takes to split a module out

This is analysis, not a task list. Nothing here is executed — no code in this
repo changes because of this document. It exists to answer the question a
"modular monolith" claim invites and usually never answers concretely: **if
you had to pull one module out into its own service, what would actually
break, and what's the real cost?**

Being honest about that cost is the point. A boundary that's cheap to draw on
paper but expensive to actually cross isn't a real boundary — writing down
exactly where the expense is is what makes the claim checkable instead of
aspirational.

## Case study: `orders`

`orders` is the module to reason about, not `users` or `products`, because
it's the one that exercises every cross-module pattern this template has:
`UnitOfWork` (via `OrderFacade.place_order`), a published domain event
(`OrderPlaced`), and a `BackgroundTasks` side effect
(`_notify_fulfillment` in `app/api/v1/orders.py`). If extraction is cheap
anywhere, it's `users` — see [Which module is actually easiest](#which-module-is-actually-easiest-to-extract-first)
at the end. `orders` is the stress test.

## What already transfers cleanly

This is the part worth taking credit for — it's the direct payoff of the
boundary discipline documented in [architecture.md](architecture.md):

- **`public_api.py` is already the service's future API contract.**
  `OrderPublicApiProtocol`'s three methods (`create_order`, `get_order_by_id`,
  `get_orders_by_user`) are already the only way anything outside `orders`
  touches it. Turning them into REST/gRPC endpoints instead of Python method
  calls is a mechanical translation of an interface that's already minimal and
  already stable — nobody has to go hunting through `service.py`/`repository.py`
  to figure out what the "real" surface is, because outside code was never
  allowed to depend on those anyway.
- **`schemas.py` becomes the wire format, unchanged.** `OrderCreateRequest`/
  `OrderResponse` are already Pydantic models with no SQLAlchemy leakage —
  they're already what a REST API's request/response bodies should look like.
- **`models.py`, `repository.py`, `service.py` move as a unit, untouched.**
  Nothing outside `orders` imports them (enforced by `.importlinter`'s
  `orders-internals` contract) and nothing outside `orders` ever will —
  extraction doesn't change who's allowed to touch them, because the answer
  was already "only `orders`."
- **The database is already physically separated.** On PostgreSQL, `orders`
  already lives in its own schema (see
  [database.md](database.md#schema-per-module-isolation-postgresql)), and its
  migrations already live in their own directory
  (`alembic/versions/orders/` — see
  [database.md](database.md#per-module-migration-directories)). Pointing a new
  service at its own physical database instance instead of a schema inside a
  shared one is a connection-string change and a `pg_dump`/`pg_restore`, not a
  schema redesign.
- **`orders` already treats `user_id`/`product_id` as opaque foreign
  identifiers, not joined data.** `Order.user_id` and `Order.product_id` are
  plain indexed columns, not foreign keys — see
  [`app/modules/orders/README.md`](../app/modules/orders/README.md#why-no-foreign-keys-unlike-products)
  for why this was already the deliberate choice, for a reason (order is a
  receipt, not a cascade target) that had nothing to do with extraction at the
  time. That it also happens to be exactly the shape a cross-service reference
  needs — an opaque ID, no possibility of a cross-database `JOIN` or cascade
  — is the extraction lens validating a decision made for a different reason.

## What breaks, and what actually has to change

### 1. `public_api` calls stop being free

`OrderFacade.place_order` currently calls `self._user_api.get_user_by_id(...)`
and gets an answer in-process, in microseconds, with a well-defined set of
failure modes (`UserError`'s union of domain errors — not found, etc.).
Turn `UserPublicApiProtocol` into an HTTP client and every one of those calls
gains a failure mode that doesn't exist today: the network. Timeout,
connection refused, 503 from an overloaded `users` service, a partial read on
a slow response. None of that fits into `UserError`'s current union type —
extraction means designing (and testing) what a facade does when the
*call itself* fails, not just when the callee returns a domain `Err`. Retries,
circuit breakers, and timeout budgets become real design decisions instead of
non-issues.

### 2. `UnitOfWork`'s atomic guarantee stops being available

This is the one that actually hurts. `OrderFacade.place_order` does four
things inside a single `UnitOfWork` — reads the user, reads the product,
reserves stock (a write to `products`), creates the order (a write to
`orders`) — and commits exactly once. That's one Postgres transaction across
two schemas, which is why [`test_place_order_rolls_back_stock_on_insufficient_stock`](testing.md#why-test_place_order_rolls_back_stock_on_insufficient_stock-exists)
can assert that a failed order leaves *both* the stock reservation and the
order row untouched — not "eventually consistent," genuinely atomic, verified
against real PostgreSQL.

Once `products`' stock and `orders`' row live in two different databases
owned by two different services, there is no shared transaction to open. The
options, none of them free:

- **Saga with compensation**: reserve stock (a step that can be undone),
  create the order, and if that fails, explicitly call a `release_stock`
  compensating action. This means `products` has to expose a new operation
  that doesn't exist today (`reserve_stock` currently has no inverse, because
  nothing needed one — a rollback did the job).
- **Eventual consistency with reconciliation**: accept a window where stock
  is reserved but the order isn't confirmed yet, and run a periodic job that
  finds and resolves orphaned reservations. This trades atomicity for
  throughput but requires idempotency keys and a reconciliation process that
  doesn't exist anywhere in this codebase today, because it's never been
  needed.

Either way: this is new distributed-systems engineering, not a mechanical
translation of `OrderFacade`. The atomicity `UnitOfWork` gives you for free
inside one process is *the* thing you pay for once you split across two.

### 3. `EventBus` stops being enough

`OrderPlaced` is currently published in-process, synchronously, after the
facade's own commit succeeds (see
[cross-module-communication.md](cross-module-communication.md#3-domain-events--fire-and-forget-side-effects)
for why that ordering matters). `EventBus.publish` swallows and logs a
handler's exception rather than propagating it — correct today, because a
broken subscriber is running in the same process as the publisher and would
otherwise take the request down with it.

None of that survives a process boundary:

- A subscriber outside the process needs the event delivered over a real
  message broker (Kafka, RabbitMQ, SQS, ...), not a Python list of callbacks.
- **Event schema versioning starts mattering for the first time.** Right now,
  `UserRegistered`/`OrderPlaced`'s producer and every consumer are the same
  deploy of the same code — a field rename is a single-commit refactor, not a
  compatibility question. Split across services with independent deploy
  schedules, and a producer can ship a new event shape while a consumer is
  still running the old code expecting the old one. Nothing in this
  codebase's events (`app/modules/users/events.py`,
  `app/modules/orders/events.py`) has ever needed a version field or a
  deprecation policy, because nothing has ever needed to keep two shapes
  compatible at once.
- **The dual-write problem appears.** Today, "commit the order" and "publish
  `OrderPlaced`" are two steps in one function, and if the process crashes
  between them, the event is lost but the order isn't in an inconsistent
  *database* state — a missed log line, not corrupted data. Across a network
  boundary, "write to your own database" and "publish to the broker" are two
  independent operations with two independent failure modes, and there's no
  way to make both succeed-or-fail-together without something like the
  outbox pattern (write the event to a table in the same transaction as the
  domain write, and have a separate process publish from that table). This
  template has never needed an outbox, because the "transaction" and the
  "publish" have always been able to be sequenced trivially in one process.

### 4. `OrderFacade` doesn't have anywhere to live

This is the structural one. `OrderFacade`'s entire reason to exist — per
[cross-module-communication.md](cross-module-communication.md#2-facade--unitofwork--when-you-need-an-atomic-result)
— is that it's the one place allowed to call more than one module's
`public_api` in a single operation, *because* all three modules are in the
same process. Extract `orders` (or `users`, or `products`) into its own
service, and that premise is gone: "coordinate three services" isn't a Python
class calling three methods anymore, it's the distributed-transaction problem
in [#2](#2-unitofworks-atomic-guarantee-stops-being-available) above, wearing
a different hat. The orchestration logic has to move *somewhere* — into the
extracted service itself (which then makes synchronous calls back out to the
other two, reintroducing the network-failure problem in
[#1](#1-public_api-calls-stop-being-free) for every request), into a
dedicated orchestration layer or API gateway, or into the saga from
[#2](#2-unitofworks-atomic-guarantee-stops-being-available). There's no
version of this where the facade just... becomes an HTTP client and keeps
working the same way.

### 5. Auth has to be redesigned, not just reused

`get_current_user_id` (`app/shared/security.py`) decodes a JWT locally using
`JWT_SECRET_KEY` — every module trusts the same in-process function to have
already validated the caller. A newly-extracted service either needs its own
copy of `JWT_SECRET_KEY` and the decode logic (the secret now has to be
shared and rotated across service boundaries, which is a real operational
concern this template has never had to think about), or authentication moves
to a centralized point — an API gateway that validates the token once and
forwards a trusted principal to every service — which is a piece of
infrastructure that doesn't exist in this template at all today.

### 6. `BackgroundTasks` stops meaning "same process, after the response"

`_notify_fulfillment` (`app/api/v1/orders.py`) runs *after* `place_order`'s
response is already sent, but still in the same worker process — see
[cross-module-communication.md](cross-module-communication.md#4-backgroundtasks--deferred-not-decoupled)
for why that's "deferred," not "decoupled." Once `orders` is a separate
service, "run this after the response, in-process" isn't a coherent idea
anymore for anything that depends on another service's state — it becomes a
job on a real task queue (Celery, ARQ, Dramatiq — this template's own docs
already flag this as the natural next step even before extraction, in
[cross-module-communication.md](cross-module-communication.md#4-backgroundtasks--deferred-not-decoupled)'s
closing paragraph).

### 7. Contract tests replace fakes as the source of truth

`tests/test_facade_fakes.py` proves `UserProductFacade.get_user_with_products`'s
*orchestration logic* is correct against a hand-written fake of
`UserPublicApiProtocol` — but a fake only proves the facade calls the
protocol correctly, not that the real `users` service (now a separately
deployed, separately versioned thing) actually implements that protocol the
way the fake assumes. Once modules are separate deployables, something like
consumer-driven contract tests (Pact or equivalent) has to exist to catch a
`users` service deploy that silently changed `get_user_by_id`'s response
shape — a class of bug that's structurally impossible today, because there's
only ever one copy of `UserPublicApi` running, and it's the same code the
facade was tested against.

## What this proves about the current design

Every cost above is a cost of *distribution* — network failure modes, losing
a shared transaction, event delivery guarantees, auth boundary redesign,
contract drift between independently-deployed services. None of it is a cost
of *bad module boundaries*. The parts that *do* transfer cleanly — the stable
`public_api` surface, the schema-per-module physical separation, the
already-opaque cross-module references, the fact that `service.py`/
`repository.py` were never reachable from outside to begin with — are exactly
what strong module boundaries buy you, and they're the parts a codebase
*without* this discipline would also have to redo from scratch during a real
extraction.

A modular monolith's job was never to make extraction free. It's to make sure
the only real cost left, when and if you actually pay it, is the
distributed-systems problem itself — not a mess of accidental coupling on top
of it.

## Which module is actually easiest to extract first

Not `orders` — `orders` was the stress test precisely because it depends on
both other modules. Per
[`app/modules/users/README.md`](../app/modules/users/README.md#dependencies-on-other-modules),
`users` is a leaf module: nothing in it imports from `products` or `orders`,
and nothing in the codebase's *design* depends on `users` being reachable
in-process except one thing —
[`Product.created_by_user_id`](database.md#the-one-deliberate-cross-module-foreign-key),
a real cross-schema foreign key with `ON DELETE CASCADE`, documented in
database.md as a deliberate exception to the no-cross-module-join rule,
justified specifically because `EventBus`'s swallowed exceptions make it the
wrong tool for an integrity guarantee. Extracting `users` means that FK loses
its database-level enforcement and the cascade delete has to become an
explicit, reliable mechanism again (a saga, or an outbox-backed event with a
retry/reconciliation policy — the same shape of problem as
[#2](#2-unitofworks-atomic-guarantee-stops-being-available) above, just
triggered by a delete instead of an order). That single FK is the one place
where this template's own documented tradeoff (accept a narrow, physical
coupling in exchange for an integrity guarantee `EventBus` can't provide) is
exactly the bill that comes due first.

## Non-goals of this document

- Not a migration guide — no steps here are meant to be executed against this
  repository.
- Not a recommendation to extract anything. The template ships, and is meant
  to be evaluated, as a single deployable monolith.
- Not exhaustive on infrastructure (service mesh, observability across
  services, deployment topology) — the scope here is specifically what
  *this codebase's own patterns* (`UnitOfWork`, `EventBus`, facades,
  `BackgroundTasks`, `public_api`) cost or don't cost when a process boundary
  is drawn through them.
