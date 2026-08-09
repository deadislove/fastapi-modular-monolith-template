# products module

Bounded context for the product catalog: listings, pricing, stock, and ownership.

## Owns

- **Table**: `products` — schema `products` in PostgreSQL (`public` in SQLite
  dev/test). See
  [`docs/architecture.md`](../../../docs/architecture.md#enforcing-boundaries).

## Public surface

External callers (other modules, facades, `app/api/`) may only import from these
four files. Everything else (`repository.py`, `service.py`) is private and blocked
by `.importlinter` at the root.

| File | Contents |
|------|----------|
| `public_api.py` | `ProductPublicApi` (and `ProductPublicApiProtocol`) — the only entry point. See its docstrings for the `session`/`UnitOfWork` and `session_factory` contracts. |
| `schemas.py` | `ProductCreateRequest`, `ProductUpdateRequest`, `ProductResponse` |
| `errors.py` | `ProductNotFoundError`, `ProductForbiddenError` (under the `ProductError` union) |
| `models.py` | `Product` — the entity type `public_api.py` returns. Treat it as a read-only value object outside this module. |

## Published events

None yet. If you add one (e.g. `ProductCreated`), follow the pattern in
`users/events.py` and wire the subscriber in `app/main.py` — see
[`docs/cross-module-communication.md`](../../../docs/cross-module-communication.md#3-domain-events--fire-and-forget-side-effects).

## Dependencies on other modules

`products` depends on `users`:

- **Application level**: `UserProductFacade` calls `UserPublicApi.get_user_by_id`
  before creating a product on someone's behalf (see
  `app/facades/user_product_facade.py`). This module's own code never imports
  `users.public_api` directly — only the facade orchestrates across both.
- **Database level**: `Product.created_by_user_id` is a real `ForeignKey("users.id",
  ondelete="CASCADE")`. This is a deliberate, narrow exception to "no cross-module
  joins": it buys referential integrity and an automatic cascade delete (delete a
  user, their products go with them) that would otherwise have to be reimplemented
  in application code — and our event bus (`app/shared/events.py`) intentionally
  swallows handler exceptions, which makes it the wrong tool for an integrity
  guarantee like this one. In PostgreSQL, with schema-per-module, this becomes a
  genuine cross-schema foreign key (`products.products` → `users.users`); that's the
  visible cost of the tradeoff, not a bug. Full writeup, including how this was
  verified end-to-end against a real PostgreSQL instance:
  [`docs/database.md`](../../../docs/database.md#the-one-deliberate-cross-module-foreign-key).
