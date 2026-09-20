import logging

from bunsho.logging_setup import configure_logging


def test_configure_logging_sets_root_level() -> None:
    root = logging.getLogger()
    previous_level, previous_handlers = root.level, list(root.handlers)
    try:
        configure_logging("DEBUG")
        assert root.level == logging.DEBUG
        configure_logging("WARNING")
        assert root.level == logging.WARNING
        assert len(root.handlers) == 1  # force=True replaced the old handler
    finally:
        root.handlers[:] = previous_handlers
        root.setLevel(previous_level)


def test_configure_logging_without_force_keeps_existing_handlers() -> None:
    root = logging.getLogger()
    previous_level, previous_handlers = root.level, list(root.handlers)
    marker = logging.NullHandler()
    try:
        root.handlers[:] = [marker]
        configure_logging("WARNING", force=False)
        assert root.handlers == [marker]
    finally:
        root.handlers[:] = previous_handlers
        root.setLevel(previous_level)
