"""Pure-Python RFC 9562 UUIDv7 generator."""

from __future__ import annotations

import os
import time
from uuid import UUID

_VERSION_BITS = 0x7 << 12
_VARIANT_BITS = 0b10 << 62


def uuid7(timestamp: int | None = None, nanos: int | None = None) -> UUID:
    if timestamp is None:
        nanoseconds = time.time_ns()
    else:
        nanoseconds = timestamp * 1_000_000_000 + (nanos or 0)
    unix_ts_ms = nanoseconds // 1_000_000
    random_bytes = os.urandom(10)
    timestamp_bytes = (unix_ts_ms & 0xFFFFFFFFFFFF).to_bytes(6, "big")
    random_a = int.from_bytes(random_bytes[0:2], "big") & 0x0FFF
    version_bytes = (_VERSION_BITS | random_a).to_bytes(2, "big")
    random_b = int.from_bytes(random_bytes[2:10], "big") & ((1 << 62) - 1)
    variant_bytes = (_VARIANT_BITS | random_b).to_bytes(8, "big")
    return UUID(bytes=timestamp_bytes + version_bytes + variant_bytes)


__all__ = ["uuid7"]
