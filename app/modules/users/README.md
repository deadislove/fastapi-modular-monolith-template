# users module

Bounded context for identity: credentials, authentication, and account records.

## Owns

- **Table**: `users` — schema `users` in PostgreSQL (`public` in SQLite dev/test,
  where cross-schema separation isn't modeled). See
  [`docs/architecture.md`](../../../docs/architecture.md#enforcing-boundaries) for why.

## Public surface

External callers (other modules, facades, `app/api/`) may only import from these
four files. Everything else (`repository.py`, `service.py`) is private and blocked
by `.importlinter` at the root.

| File | Contents |
|------|----------|
| `public_api.py` | `UserPublicApi` (and `UserPublicApiProtocol`) — the only entry point. See its docstrings for the `session`/`UnitOfWork` and `session_factory` contracts. |
| `schemas.py` | `UserRegisterRequest`, `UserLoginRequest`, `UserUpdateRequest`, `UserResponse`, `TokenResponse` |
| `errors.py` | `UserNotFoundError`, `UserEmailConflictError`, `UserUsernameConflictError`, `InvalidCredentialsError`, `UserInactiveError` (all under the `UserError` union) |
| `models.py` | `User` — the entity type `public_api.py` returns. Treat it as a read-only value object outside this module; never write to it or query it directly. |

## Published events

| Event | When | Defined in |
|-------|------|------------|
| `UserRegistered` | After a registration transaction commits | `events.py` |

Subscribers are wired at the composition root (`app/main.py`), not here — this
module never knows who (if anyone) is listening. See
[`docs/cross-module-communication.md`](../../../docs/cross-module-communication.md#3-domain-events--fire-and-forget-side-effects).

## Dependencies on other modules

None. `users` is a leaf module — nothing in it imports from `products`. `products`
depends on `users` (a product row's `created_by_user_id` is a real, DB-level foreign
key into this module's table — see `products/README.md` for why that's an
intentional exception to the "no cross-module joins" rule).
