# Testing

```bash
pytest              # test suite
ruff check .         # lint
lint-imports         # architecture boundary contracts (also runs inside pytest)
```

`.github/workflows/ci.yml` runs exactly these three on every push/PR, plus a
second job that applies both Alembic migrations against a real PostgreSQL
service container — the same schema-per-module path described in
[database.md](database.md#schema-per-module-isolation-postgresql), checked on
every push instead of only when someone remembers to.

## Test suite map

| File | Level | Covers |
|------|-------|--------|
| `test_users.py` / `test_products.py` | HTTP (via `httpx.AsyncClient` + `ASGITransport`) | Per-module request/response behavior, one module at a time |
| `test_facade.py` | HTTP setup, facade called directly | Cross-module composition (`get_user_with_products`), and that `UnitOfWork` actually rolls back when a write should be rejected |
| `test_orders.py` | HTTP | The three-module `OrderFacade` flow: placing an order, insufficient stock, ownership checks, that a failed stock reservation leaves both `products`' stock and `orders`' row count unchanged, and that the `BackgroundTasks` fulfillment notification is actually scheduled (via `unittest.mock.patch`, not log-scraping — see below) |
| `test_events.py` | Unit (`EventBus` in isolation) + integration | `EventBus` semantics (dispatch, no-subscriber no-op, one handler's failure doesn't block others, unsubscribe), plus a real HTTP registration proving the `main.py` subscriber wiring actually fires |
| `test_public_api_di.py` | Unit | Constructing a `UserPublicApi` with an explicit `session_factory`, fully isolated from the process-wide `AsyncSessionFactory` global |
| `test_architecture.py` | Static analysis, run as a test | Executes `.importlinter`'s contracts via `importlinter.cli.lint_imports()` and asserts success |
| `test_error_envelope.py` | HTTP | Every error shape (404 domain error, 422 validation, 401 auth, 429 rate limit) uses the same `{"error": {"code", "message"}}` envelope |
| `test_health.py` | HTTP | `/health` is always 200; `/health/ready` reflects real DB reachability (including a simulated-outage case) |

`tests/conftest.py` wires an in-memory SQLite database (`sqlite+aiosqlite:///:memory:`)
shared across the whole test session, and patches `app.shared.database.AsyncSessionFactory`
to point at it *before* the app's module-level singletons (`user_public_api`,
`product_public_api`, ...) are constructed — see
[cross-module-communication.md](cross-module-communication.md#session-factory-injection)
for why that ordering, and that specific mechanism, is what makes it work.

## Why `test_create_product_for_user_rolls_back_when_user_missing` exists

This is the regression test for `UnitOfWork`'s core guarantee: call the facade with
a nonexistent `user_id`, assert the `Result` is `Err`, then assert the product
table's row count is unchanged. Without this test, a future change that broke the
"default to rollback" behavior (see [database.md](database.md#unitofwork)) would
only show up as silent data corruption in production, not a failing test.

## Why `test_place_order_rolls_back_stock_on_insufficient_stock` exists

The facade rollback test above proves `UnitOfWork` works for one module's write
guarded by another module's read. This test proves the stronger claim: it holds
when **two different modules both write** inside the same `UnitOfWork`
(`products`' stock reservation, `orders`' new row). Ordering more than the
available stock must leave both untouched — not just the order missing, but the
stock reservation that ran first also undone. This was also checked by hand
against real PostgreSQL when `orders` was added; see
[database.md](database.md#verifying-against-real-postgresql-what-was-actually-checked).

## Why `test_architecture.py` exists

`import-linter`'s contracts (see
[architecture.md](architecture.md#enforcing-boundaries)) are only useful if someone
actually runs `lint-imports`. Wrapping the same check as a pytest test means a
boundary violation shows up in `pytest`'s output — the command most people already
run before committing — instead of depending on a separate step nobody remembers.
The test calls `importlinter.cli.lint_imports()` directly (not a subprocess) so it
doesn't depend on the `lint-imports` console script being on `PATH`.

## A gotcha this suite already ran into: the rate limiter is process-wide

`tests/conftest.py` has an `autouse` fixture, `_reset_rate_limiter`:

```python
@pytest_asyncio.fixture(autouse=True)
def _reset_rate_limiter():
    from app.shared.rate_limiter import limiter
    limiter.reset()
```

slowapi's `Limiter` (`app/shared/rate_limiter.py`) keeps its request counters in a
single process-wide in-memory store — the same store for every test in the session,
regardless of which file or which fake user they use. `/api/v1/users/register` is
limited to `10/minute`. Early in this project's test-suite growth, that limit was
comfortably under the total number of `/register` calls across all tests combined;
once a few more test files were added, the *cumulative* count crossed 10 partway
through the session, and a test with nothing to do with rate limiting
(`test_register_duplicate_email`, asserting a `409`) started intermittently seeing
a `429` instead — not because its own logic was wrong, but because of how many
requests unrelated earlier tests happened to have made.

The fix is the `autouse` fixture above: reset the limiter's counters before every
test, so each test gets its own budget regardless of execution order or how large
the suite grows. If you add a new test that hits a rate-limited endpoint many times
in a loop, you still don't need to think about this — the reset happens
automatically before your test runs.

## Another gotcha: shared test data across a file

The in-memory SQLite database persists for the whole test session (one
`setup_test_db` fixture, `scope="session"`), not per test. Registering the same
email/username twice in the same test file will `409` the second time. Two patterns
are used to deal with this:

- `test_users.py` / `test_products.py` intentionally reuse one fixed payload across
  every test in the file, and none of the tests that don't specifically test
  registration assert on the registration response — they only need *a* valid user
  to exist, and don't care if it already did from an earlier test in the file.
- `test_facade.py` needs each test's registration to actually succeed (it reads the
  returned `id`), so each test uses its own unique username instead
  (`_register_payload(username)` builds a fresh payload per call).

Pick whichever fits: if you don't need the registration response, reuse is fine and
matches the existing tests; if you do, give the test its own identity.

## A gotcha found by running the real server, not by testing: silent app loggers

Every `logger.info(...)` call in this codebase — the `EventBus` subscribers in
`app/main.py`, the `BackgroundTasks` handler in `app/api/v1/orders.py`, the
exception handler's `logger.exception(...)` — produced **no output at all**
under plain `uvicorn app.main:app`, discovered only by actually running the
server and grepping its log, not by reading the code or running `pytest`.
uvicorn configures its own `"uvicorn"` / `"uvicorn.access"` loggers but attaches
no handler to the root logger, so `app.*` loggers (which propagate to root by
default) had nowhere to go. Fixed with one `logging.basicConfig(...)` call in
`app/main.py`. This is exactly the class of bug `pytest` can't catch — nothing
asserts on log *visibility* — which is why actually running the app (`uvicorn
app.main:app`, per the root README's Quick Start) and driving a real request
through it matters even with a fully green test suite.

## Why `test_place_order_schedules_fulfillment_background_task` uses `unittest.mock.patch`, not `caplog`

The first version of this test used pytest's `caplog` fixture to look for the
background task's log line. It failed even though the task demonstrably ran
(confirmed via the real server, above) — `caplog`'s capture doesn't reliably
line up with a `BackgroundTasks` callback's execution window when the app is
driven through `httpx.ASGITransport` in-process. Patching
`app.api.v1.orders._notify_fulfillment` with `unittest.mock.AsyncMock` and
asserting `assert_awaited_once_with(...)` is both more reliable and more
precise — it checks the exact arguments the background task was scheduled
with, not just that some matching text appeared somewhere in a log.
