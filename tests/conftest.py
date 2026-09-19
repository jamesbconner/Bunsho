"""Make shared fixtures from ``tests.base`` available to every test module."""

from tests.base import app_config, quiet_logger

__all__ = ["app_config", "quiet_logger"]
