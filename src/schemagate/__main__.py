# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""``python -m schemagate`` -- same as the ``schemagate`` console script."""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
