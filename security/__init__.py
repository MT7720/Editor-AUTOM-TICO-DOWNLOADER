"""Rotinas de segurança e proteção em tempo de execução."""

from .runtime_guard import SecurityViolation, enforce_runtime_safety

__all__ = ["SecurityViolation", "enforce_runtime_safety"]
