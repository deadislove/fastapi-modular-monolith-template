# orders module

Bounded context for placing and viewing orders. The third module in this
template, added specifically to prove the patterns in `docs/` hold up past two
modules — it's the only module that depends on **both** `users` and `products`.

## Owns

- **Table**: `orders` — schema `orders` in PostgreSQL (`public` in SQLite dev/test).

## Public surface

| File | Contents |
|------|----------|
| `public_api.py` | `OrderPublicApi` (and `OrderPublicApiProtocol`) — the only entry point. |
| `schemas.py` | `OrderCreateRequest`, `OrderResponse` |
| `errors.py` | `OrderNotFoundError` (under the `OrderError` union) |
| `models.py` | `Order` — the entity type `public_api.py` returns. Treat it as a read-only value object outside this module. |

Everything else — including `subscribers.py` — is private and blocked by
`.importlinter` at the root, same as `repository.py`/`service.py`.

## Published events

| Event | When | Defined in |
|-------|------|------------|
| `OrderPlaced` | After an order and its stock reservation both commit | `events.py` |

Published by `OrderFacade.place_order` (not `OrderPublicApi.create_order`) —
see [Dependencies](#dependencies-on-other-modules) for why. This module
self-registers its own reaction to `OrderPlaced` in `subscribers.py`; only
`app/main.py` (the composition root) may call it, and a subscription from
another module would still have to be wired there instead. See
[`docs/cross-module-communication.md`](../../../docs/cross-module-communication.md#where-subscriptions-are-wired-up).

## Dependencies on other modules

`orders` depends on both `users` and `products`, coordinated by
`OrderFacade` (`app/facades/order_facade.py`), never by this module's own
code importing either directly:

1. Validate the user exists (`UserPublicApi.get_user_by_id`).
2. Read the product's price (`ProductPublicApi.get_product_by_id`).
3. Reserve stock (`ProductPublicApi.reserve_stock` — decrements `stock`,
   fails with `InsufficientStockError` if not enough is available).
4. Create the order (`OrderPublicApi.create_order`).

All four calls share one `UnitOfWork`/session, and the facade only commits
after step 4 succeeds — a stock reservation can never be left committed
without its order, or vice versa. This is a stricter test of the pattern than
`UserProductFacade`: that one writes to a single module after a read from
another; this one writes to **two** different modules' tables atomically.

Because the facade — not `OrderPublicApi.create_order` — owns the commit here,
`create_order` does not publish `OrderPlaced` in that path (its own `owns`
flag is `False`, since it received an external session). The facade publishes
it instead, once its own commit has actually succeeded. See
[`docs/cross-module-communication.md`](../../../docs/cross-module-communication.md)
for the general pattern this follows.

### Why no foreign keys, unlike `products`

`Order.user_id` and `Order.product_id` are plain indexed integer columns —
**not** `ForeignKey`s, unlike `Product.created_by_user_id` (see
`app/modules/products/README.md`). This is the normal case; products' FK is
the deliberate, narrow exception. Two reasons this module doesn't take the
same shortcut:

- **Business correctness, not just architecture**: deleting a product should
  not delete the historical orders that reference it — an order is a receipt.
  A `ForeignKey(..., ondelete="CASCADE")` here would be actively wrong, not
  just architecturally impure.
- Referential integrity is instead guaranteed by the facade validating both
  IDs *inside the same transaction* that creates the order — see
  [database.md's `UnitOfWork` section](../../../docs/database.md#unitofwork).
