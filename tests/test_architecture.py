import os
from pathlib import Path

from importlinter.cli import EXIT_STATUS_SUCCESS, lint_imports

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_module_boundaries_are_respected() -> None:
    """
    Fails the suite if a module's internals (repository.py/service.py) are
    imported from outside the module, or the api -> facades -> modules -> shared
    layering is violated. Rules live in .importlinter — see README's "Enforcing
    boundaries" section. Running this as a pytest test (in addition to `lint-imports`
    on its own) keeps the architecture contract visible in the same command as the
    rest of the suite, so it can't silently rot unnoticed.
    """
    original_cwd = Path.cwd()
    os.chdir(REPO_ROOT)
    try:
        status = lint_imports(config_filename=str(REPO_ROOT / ".importlinter"))
    finally:
        os.chdir(original_cwd)

    assert status == EXIT_STATUS_SUCCESS