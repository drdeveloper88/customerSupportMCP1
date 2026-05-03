"""
Shared SlowAPI rate-limiter instance.

Defined here (not in main.py) to avoid circular imports when endpoint
modules need to apply @limiter.limit() decorators at class/module level.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from core.config import REDIS_URL

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=REDIS_URL,
    default_limits=[],
)
