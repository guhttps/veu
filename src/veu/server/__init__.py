"""Servidor HTTP do Véu (pip install \"veu[servidor]\")."""

from veu.server.app import create_app, resolve_route, run

__all__ = ["create_app", "resolve_route", "run"]
