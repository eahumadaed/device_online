"""Unified online-status providers for DVR/NVR P2P cloud checks."""

from .providers import DeviceProvider, get_provider

__all__ = ["DeviceProvider", "get_provider"]
