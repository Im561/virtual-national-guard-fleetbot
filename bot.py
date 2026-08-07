from __future__ import annotations

import asyncio
import sys

from fleetbot.app import ConfigurationError, main


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
