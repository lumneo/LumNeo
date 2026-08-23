"""Permission adapters for Hardware OS."""

from .local_policy import LocalPermissionGate, LocalPermissionPolicyConfig

__all__ = ("LocalPermissionGate", "LocalPermissionPolicyConfig")
