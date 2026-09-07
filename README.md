# IAAI

**Idea Audit + Artificial Intelligence**

IAAI is at the **early architecture / prototype stage**. It is intended to become a local
research engine for independent, evidence-based analysis of business, startup, technology,
and scientific ideas.

The planned direction includes traceable evidence, FOR/AGAINST research, recursive research,
and replaceable model and provider integrations. IAAI will not reduce a complex idea to a
"magic" startup score. The initial MVP is intended to remain usable locally with no required
paid APIs, hosted services, or cloud infrastructure.

This repository currently contains only the project foundation. The research engine, model
integrations, search, evidence analysis, reports, and user interface have not yet been
implemented. Architecture will be defined in a separate review before those components are
built.

## Development setup

IAAI requires Python 3.11 or newer.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
ruff check .
pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) before proposing changes. New GitHub users can start
with [docs/GITHUB_WORKFLOW.md](docs/GITHUB_WORKFLOW.md).

## License

Licensed under the [Apache License 2.0](LICENSE).
