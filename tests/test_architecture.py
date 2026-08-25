import logging
import os
from pathlib import Path

from importlinter.cli import EXIT_STATUS_SUCCESS, lint_imports

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_module_boundaries_are_respected() -> None:
    """Runs the .importlinter contracts as a normal test, so a boundary
    violation shows up alongside the rest of the suite."""
    # lint_imports() calls logging.config.dictConfig(...) internally with
    # that library's default disable_existing_loggers=True, which silently
    # sets .disabled = True on every logger that already existed (app.*,
    # sqlalchemy.engine, ...) for the rest of the process — not just this
    # test. Save and restore each one so a test that runs after this one
    # (and relies on logging, e.g. via caplog) isn't silently broken by it.
    loggers = [logging.getLogger(name) for name in logging.root.manager.loggerDict]
    disabled_before = {logger: logger.disabled for logger in loggers}

    original_cwd = Path.cwd()
    os.chdir(REPO_ROOT)
    try:
        status = lint_imports(config_filename=str(REPO_ROOT / ".importlinter"))
    finally:
        os.chdir(original_cwd)
        for logger, was_disabled in disabled_before.items():
            logger.disabled = was_disabled

    assert status == EXIT_STATUS_SUCCESS