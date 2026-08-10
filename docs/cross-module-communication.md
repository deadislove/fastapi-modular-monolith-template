# Cross-module communication

"Modules only talk through `public_api.py`" tells you what's forbidden, not what to
reach for instead. This project has three sanctioned patterns, each suited to a
different question:

| Pattern | Question it answers | Caller gets a result? | Where it lives |
|---|---|---|---|
| Direct `public_api` call | "I need this one module's data/action" | Yes | Anywhere (router, another module, a facade) |
| Facade + `UnitOfWork` | "I need two modules to do something *together*, atomically, and I need to know if it worked" | Yes | `app/facades/` only |
| Domain event | "Module A wants module B (or C, or nobody) to react, but A doesn't need to know or wait" | No | Published in the module, subscribed at the composition root |

## 1. Direct `public_api` calls

The default. A router or another module calls a module's `public_api` singleton
directly:

```python
from app.modules.users.public_api import user_public_api

result = await user_public_api.get_user_by_id(user_id)
```

No orchestration, no shared transaction — just one module's `Result` coming back.
Most of `app/api/v1/*.py` is this.

## 2. Facade + `UnitOfWork` — when you need an atomic result

A **Facade** is the only code allowed to call into more than one module's
`public_api` within a single operation. Reach for it when the caller needs a
combined result back — e.g. `UserProductFacade` (`app/facades/user_product_facade.py`)
assembling a `UserWithProducts` composite, or validating a user exists before
creating a product on their behalf. `OrderFacade`
(`app/facades/order_facade.py`) is the same pattern one module further: placing
an order reads from `users`, reads and writes `products` (reserving stock), and
writes `orders`, all inside one `UnitOfWork` — proof the pattern isn't
two-module-specific.

Every `public_api.py` method accepts an optional `session` parameter. Called
without it — the common case — the method opens and commits its own session,
exactly as if the module were being used in isolation. A facade that needs an
**atomic** write across two modules instead opens a `UnitOfWork`, passes the shared
session into each call, and commits explicitly once it has confirmed success:

```python
from app.shared.database import UnitOfWork

async def create_product_for_user(self, user_id: int, ...) -> Result[Product, ...]:
    async with UnitOfWork() as session:
        user_result = await self._user_api.get_user_by_id(user_id, session=session)
        if user_result.is_err():
            return Err(user_result.err())

        result = await self._product_api.create_product(data, user_id, session=session)
        if result.is_ok():
            await session.commit()
        return result
```

### Why `UnitOfWork` defaults to rollback, not commit

A naive "commit unless an exception was raised" implementation is wrong for this
codebase specifically, because of the [Result pattern](architecture.md#result-pattern-over-exceptions):
failure is a returned `Err`, not a raised exception. If `UnitOfWork` auto-committed
on any exception-free exit, a facade that fetched a user, flushed a partial write,
then decided to return `Err` for a domain reason (not an exception) would still
have that partial write committed on the way out — silent data corruption, not a
crash you'd notice.

So `UnitOfWork` inverts the default: it **always rolls back on exit** — success,
`Err`, or a raised exception alike — unless the caller explicitly called
`session.commit()` first. A forgotten commit fails safe (nothing persisted) instead
of failing dangerous (a partial write persisted). See
`app/shared/database.py`'s `UnitOfWork` docstring and
`UserProductFacade.create_product_for_user` for the full pattern, and
`tests/test_facade.py::test_create_product_for_user_rolls_back_when_user_missing`
for the regression test that pins this behavior down.

### Who publishes the event when a Facade drives the `UnitOfWork`

`UserPublicApi.register_user` publishes `UserRegistered` itself — but only in the
branch where it opened and committed its own session (`owns=True`; see
[Domain events](#3-domain-events--fire-and-forget-side-effects) below). When a
facade passes in an external session, that method's `owns` is `False`, it never
commits, and so it correctly never publishes either — publishing has to happen
strictly after a successful commit, and the individual `public_api` call inside
a `UnitOfWork` doesn't know when (or whether) that commit will happen.

`OrderFacade.place_order` is the concrete case: it drives the `UnitOfWork` and
owns the commit, so *it* — not `OrderPublicApi.create_order` — publishes
`OrderPlaced`, once its own `session.commit()` has actually succeeded. If you add
a facade method that should raise an event, this is the pattern: publish from the
facade, after its commit, not from the module method it called.

### Session factory injection

Every `public_api.py` class also accepts an optional `session_factory` in its
constructor:

```python
class UserPublicApi:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory
```

The module singletons (`user_public_api`, `product_public_api`, `order_public_api`
— instantiated at the bottom of each `public_api.py`) leave it unset. That means they resolve
`app.shared.database.AsyncSessionFactory` lazily, by name, on every call — which is
what lets `tests/conftest.py` point the *entire app* at an in-memory SQLite database
by patching that one module attribute before the app object is even built.

For a test that wants an isolated instance instead of relying on that process-wide
global, construct one directly:

```python
isolated_api = UserPublicApi(session_factory=TestSessionFactory)
```

See `tests/test_public_api_di.py`.

## 3. Domain events — fire-and-forget side effects

A domain event is for when a module just needs to say "this happened," without
knowing or caring whether anyone reacts — logging, sending a welcome email, warming
a cache. Unlike a Facade, **the publisher gets nothing back** and never learns
whether a subscriber ran, succeeded, or even exists.

`app/shared/events.py` provides an in-process `EventBus`:

```python
class EventBus:
    def subscribe(self, event_type, handler) -> None: ...
    def unsubscribe(self, event_type, handler) -> None: ...
    async def publish(self, event: DomainEvent) -> None: ...
```

Each module defines the events it publishes next to itself, e.g.
`app/modules/users/events.py`:

```python
@dataclass(frozen=True)
class UserRegistered(DomainEvent):
    user_id: int
    email: str
```

`UserPublicApi.register_user` publishes `UserRegistered` **after** its own
transaction commits — publishing before commit would let a subscriber observe a
user that isn't durably saved yet.

### Where subscriptions are wired up

Subscribers are registered at the **composition root**, `app/main.py` — the one
place in the codebase allowed to import both a module's event types and the
cross-cutting handlers that react to them. Modules never import each other's
`events.py` directly; that would just be the forbidden cross-module coupling with
extra steps.

```python
# app/main.py
async def _log_user_registered(event: UserRegistered) -> None:
    logger.info("User registered: id=%s email=%s", event.user_id, event.email)

def register_event_subscribers() -> None:
    event_bus.subscribe(UserRegistered, _log_user_registered)
```

Add a new side effect (e.g. "send a welcome email") by writing a handler and
subscribing it in `main.py`. The `users` module doesn't change.

### Why handler exceptions are swallowed — and what that rules out

`EventBus.publish` catches and logs any exception a handler raises, then continues
to the next handler:

```python
async def publish(self, event: DomainEvent) -> None:
    for handler in self._handlers[type(event)]:
        try:
            await handler(event)
        except Exception:
            logger.exception("Event handler %r failed for %r", handler, event)
```

This is deliberate: a broken *optional* side effect (a flaky email provider, a bug
in a new subscriber) should never take down the request that published the event.

The direct consequence is that **this event bus is the wrong tool for anything that
needs a guarantee** — a cascade delete, a balance update, anything where "the
handler silently failed" is a data-integrity bug rather than a missed nice-to-have.
That's precisely why `Product.created_by_user_id` stays a real, enforced
`ForeignKey(..., ondelete="CASCADE")` instead of "delete the user, publish
`UserDeleted`, have `products` subscribe and delete their rows" — see
[database.md](database.md#the-one-deliberate-cross-module-foreign-key) for that
tradeoff in full. `orders` is the contrast: it references `users`/`products` by
plain id, no FK, because a Facade validates both ids inside the same transaction
that writes the order — see `app/modules/orders/README.md`.

## Decision guide

- Need one module's data or to perform one module's action? → **direct `public_api`
  call**.
- Need two modules to do something together and must know if it worked, especially
  if it involves more than one write that has to succeed or fail as a unit? →
  **Facade + `UnitOfWork`**.
- Need to notify interested parties that something happened, and it's fine if
  nobody's listening or a listener fails? → **domain event**.
- Need a hard guarantee (referential integrity, an atomic multi-row invariant) that
  spans two modules' tables? → that's the one case where a narrow, explicit,
  documented DB-level constraint (like the products→users foreign key) can be the
  right call over any of the above three — see
  [database.md](database.md#the-one-deliberate-cross-module-foreign-key).
