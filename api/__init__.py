"""Make `api` a package so `from api.app import app` works in tests and CI."""

__all__ = ["app"]
