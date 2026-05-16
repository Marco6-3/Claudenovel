#!/usr/bin/env python3
from __future__ import annotations

import sys

from agent_writer.cli import main


def enable_utf8_stdio() -> None:
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


if __name__ == "__main__":
    enable_utf8_stdio()
    raise SystemExit(main())
