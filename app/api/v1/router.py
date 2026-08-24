import importlib
import pkgutil

from fastapi import APIRouter

import app.api.v1

api_v1_router = APIRouter(prefix="/api/v1")


def discover_routers() -> None:
    """Imports every sibling app/api/v1/<name>.py file and mounts its
    `router` attribute — must run after app.main's discover_modules(), since
    each router file resolves its module's contract from module_registry at
    import time."""
    for _, name, is_pkg in pkgutil.iter_modules(app.api.v1.__path__):
        if is_pkg or name == "router":
            continue
        router_module = importlib.import_module(f"app.api.v1.{name}")
        # getattr, not router_module.router: a dynamically imported module has
        # no static type, so direct attribute access would fail mypy instead.
        api_v1_router.include_router(getattr(router_module, "router"))  # noqa: B009
