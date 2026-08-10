import os
from pathlib import Path

from importlinter.cli import EXIT_STATUS_SUCCESS, lint_imports

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_module_boundaries_are_respected() -> None:
    """Runs the .importlinter contracts as a normal test, so a boundary
    violation shows up alongside the rest of the suite."""
    original_cwd = Path.cwd()
    os.chdir(REPO_ROOT)
    try:
        status = lint_imports(config_filename=str(REPO_ROOT / ".importlinter"))
    finally:
        os.chdir(original_cwd)

    assert status == EXIT_STATUS_SUCCESS