# IAAI

**Idea Audit + Artificial Intelligence**

IAAI is at the **early architecture / prototype stage**. It is intended to become a local
research engine for independent, evidence-based analysis of business, startup, technology,
and scientific ideas.

The planned direction includes traceable evidence, FOR/AGAINST research, recursive research,
and replaceable model and provider integrations. IAAI will not reduce a complex idea to a
"magic" startup score. The initial MVP is intended to remain usable locally with no required
paid APIs, hosted services, or cloud infrastructure.

Phase 1 / Step 1 is executable: create and inspect research sessions through a local browser
UI or CLI, with immutable protocol/policy snapshots, revision history and runtime manifests
persisted in SQLite. Step 2 adds public HTML/manual acquisition, exact chunks and frozen corpus
BM25 search. **No research analysis is performed.** Evidence assessment, reports
and recursion remain unimplemented. Step 3 adds one optional local GGUF proposal model
and a human reviewer queue; candidates are not facts or evidence. See the
[local proposal guide](docs/phase1-proposal-model.md) for setup and limitations.

Architecture v0.1 is **ACCEPTED FOR EXPERIMENTAL IMPLEMENTATION**. This does not validate
the methodology: Phase 1 is a human-assisted experiment, calibration defaults remain
**UNVALIDATED**, and recursion must demonstrate benefit in a controlled A/B experiment.
Concrete future ML models remain replaceable implementations.

## Run locally

After installing (see below), from the repository directory:

```text
iaai doctor
iaai serve
```

Open http://127.0.0.1:8765 → **Новое исследование** → fill idea, scope and plain-language questions →
**Создать исследование**. Constraints are optional. Details show the policy, hashes, revision
and manifest. Step 2: open **Источники и корпус**, add a public HTML URL or import text,
include materials, choose **Зафиксировать корпус**, then search the frozen snapshot with BM25.
This is text retrieval, not a truth assessment or an analytical conclusion.
See [corpus guide](docs/phase1-corpus.md) for security, retention and limitations.
Stop with Ctrl+C; run `iaai serve` again and the same session remains.
The default database is `./runtime/iaai.db`, ignored by Git. Keep the same working directory
or use an explicit `--db` path. Never delete the runtime directory to upgrade the application.

Windows without activation: `.\.venv\Scripts\iaai.exe serve`.

```text
iaai research create --protocol examples/protocol.json
iaai research list
iaai research show RESEARCH_ID
iaai research show RESEARCH_ID --revision 1
iaai manifest show RUN_ID
iaai --db runtime/another.db doctor
```

See [Step 1 guide](docs/phase1-foundation.md) for schemas, revisions, limitations and storage.

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
