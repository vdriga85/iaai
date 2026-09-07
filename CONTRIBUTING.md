# Contributing to IAAI

Thank you for helping improve IAAI. For external contributions:

1. Fork the repository.
2. Create a focused branch such as `feature/short-name` or `fix/short-name`.
3. Make and document the change.
4. Run `ruff check .` and `pytest`.
5. Push the branch to your fork and open a Pull Request.

A Pull Request should clearly explain its purpose, pass lint and tests, and avoid unrelated
changes. Never commit secrets, private research sessions, datasets, downloaded sources,
databases, model weights, caches, or generated indexes.

Do not introduce a mandatory paid service or API without an explicit architecture decision.
Keep the core independent of particular models, search providers, databases, and cloud
platforms.
