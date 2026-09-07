# Phase 1 / Step 1: executable session foundation

This is a local engineering UI, **not an analysis engine**. Creating a session records a
`CREATED` Research, Revision 1 and Manifest v0.1. It does not start an evaluated run,
reserve hardware, acquire sources, execute policies or claim methodology validation.
The future evaluation entry point must check actual host capacity before starting work.

## Installation and UI

Python 3.11+; no Node, Docker, API keys, models or network access needed after installation.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\iaai.exe doctor
.\.venv\Scripts\iaai.exe serve
```

Open http://127.0.0.1:8765. The prototype UI is Russian; see the field guide below.
Ordinary outputs are plain-language descriptions, one per line. Typed outputs and constraint/
policy JSON are optional advanced inputs. The CLI and all persisted JSON schemas are unchanged.

The UI uses Flask routing, Jinja autoescaping and its lightweight test client. The standard
library HTTP server would require hand-building form handling, routing and template escaping;
Flask avoids creating our own web framework. It binds **only 127.0.0.1**, debug/reloader off.
No public deployment or authentication. Local Host validation and per-process CSRF sessions
prevent other websites from submitting forms to localhost. Restarting requires reloading a
previously open form. Do not expose this server via a proxy, tunnel or port forwarding.

## Architecture and dependencies

`cli.py` / `web.py` → `application.py` → typed `domain.py` / `ResearchStore` in `ports.py`.
`bootstrap.py` chooses `SQLiteResearchStore` and injects environment metadata functions.
No domain/application imports SQLite, HTML or Flask. UI does not import storage or run SQL.
The used operations are create, revise, list, get/revision, get manifest and doctor.

Two direct runtime dependencies:

- Flask >=3.1,<4: local server-rendered UI, routing, escaping, test client.
- Pydantic >=2.10,<3: strict nested schemas, immutable snapshots, explicit errors and JSON
  serialization. Handwritten equivalents would duplicate validation across many nested fields.

Transitive Flask dependencies: Werkzeug, Jinja2, MarkupSafe, itsdangerous, click, blinker;
click may use colorama on Windows. Pydantic dependencies: pydantic-core, annotated-types,
typing-extensions, typing-inspection. Existing dev dependencies remain pytest and Ruff;
no new test/browser framework. Manifests record actual installed distribution versions,
including transitives, rather than treating declared version ranges as a lockfile.

## JSON schemas and immutable history

JSON is the sole file format: stdlib parsing/encoding with Pydantic validation, no YAML/TOML
dependency. `examples/protocol.json` is a complete minimal protocol. The versioned resolved
default is `src/iaai/default-policy-v0.1.json`, packaged in the wheel.
Required fields must be present; documented optional values use explicit null/empty arrays.
Unknown fields, wrong versions, booleans in numeric fields, non-finite numbers, invalid units,
duplicate output names, missing scope, mismatched constraint/output units and invalid budgets
are rejected before persistence. No automatic unit conversion. Text constraints allow only eq.
Policy validates lane sums, reserves, cross-field budget ceilings and ordered checkpoints.

Step 1 deliberately implements only a **subset** of the architecture policy registry:
five versioned subsections, SIMPLE scheduling declarations, stop declarations, resource limits,
SQLite busy timeout and minimal evaluation declarations. These are recorded configuration,
not implementations of scheduling/stopping/evaluation. Only SQLite busy timeout is currently
operational (applied to the saving connection). Doctor/read connections use packaged defaults.
Unused model, acquisition, lease, graph and ADV switches are rejected, not silently ignored.
Adding such capabilities requires an explicit schema revision and implementation.

All defaults are UNVALIDATED. PILOT_CALIBRATED/EVALUATED require a calibration dataset
reference; that metadata is a user declaration, not certification by this application.
There are no hidden policy-derived business constraints. Schema limits (e.g. valid port,
finite numeric types) are safety/type rules, not calibration thresholds.

Snapshots are frozen, including tuple collections. Hash = SHA-256 of UTF-8 JSON with sorted
keys, compact separators, explicit nulls, finite numbers, no ASCII escaping. Hashes cover
resolved content (including IDs/versions), not filenames, and are not embedded in their own
input. Nested policies also expose `content_hash`. This is an application canonical format,
not a claim of RFC 8785 interoperability; Unicode is not normalized and list order matters.

```text
iaai research create --protocol examples/protocol.json
iaai research list
iaai research show RESEARCH_ID --revision 1
iaai manifest show RUN_ID
iaai research revise RESEARCH_ID --protocol protocol-v2.json --policy policy-v2.json
```

To revise: copy the inspected protocol/policy JSON into files; change the intended fields.
Increase the changed object's version if retaining its ID. A changed policy must include
`parent_policy_hash` equal to the previous resolved policy hash. Supply both files, even if
only one changed. Revision N+1 gets a new run ID/manifest. Historical snapshots are retained;
an optimistic current-revision check prevents concurrent writers from losing updates.
The Research summary always describes the current revision; inspecting an older revision
displays that revision's original idea/scope independently. No full event sourcing.

## Database and migrations

Default: `./runtime/iaai.db` (relative to launch directory), or global CLI `--db PATH` before
the command. Database/WAL/SHM/runtime files are ignored. Data is not encrypted; keep it local
and protected by OS permissions. No delete/update-history API is provided.

Exactly five tables: researches, protocols, policies, revisions, manifests. Protocol/policy
rows are addressed by content hash, manifest stores its hash, revisions link them. Creation
and revision writes are one transaction. Immutable table UPDATE/DELETE triggers protect
history; researches alone has a mutable current pointer/summary. This is not tamper-proof
against an administrator who can modify the DB; reads validate content hashes/references.

Settings on every connection: WAL, synchronous=FULL, foreign_keys=ON, busy_timeout=5000 ms
by default. Saving a custom policy uses that policy's validated busy timeout. WAL requires
a writable local filesystem; network/synchronized folders are not a supported deployment.

Ordered SQL migrations are in `sqlite_store.MIGRATIONS`; `PRAGMA user_version=1` and
`application_id=IAAI` identify this schema. Initialization is serialized with BEGIN IMMEDIATE;
schema statements and version advancement commit together. Existing unknown, newer or altered
schemas are rejected rather than recreated. V1 structural checks include immutability triggers.
Concurrent initialization exposed two SQLite edge cases: metadata reads now share one read
snapshot, and WAL mode transition retries SQLITE_BUSY within the configured busy-time budget.
Revision writes themselves are never blindly retried. Tests cover concurrent creation and
stale-revision rejection without lost updates.
No heavyweight migration library for one schema. Future migrations need compatibility tests
and explicit upgrade paths. Schema checking currently opens a small in-memory reference DB
per connection: intentionally simple, to revisit only if measured overhead matters.

## Manifest / diagnostics / errors

Manifest v0.1 captures research/revision/run IDs, protocol and policy hashes, UTC creation,
Git HEAD and dirty state, Python/implementation, installed distributions, OS, machine,
logical CPU count and physical RAM where available. Git is captured from the launch directory
at creation; non-Git installs report UNAVAILABLE/null. No model/corpus/extraction metadata
or chain-of-thought is fabricated. Manifest hash includes timestamp/run ID, so different
creations differ; serializing the same snapshot preserves its hash.

`iaai doctor` and `/diagnostics` call the same service. They initialize an absent DB, check
actual connection settings, schema and quick_check/foreign_key_check, and report path/free
disk/runtime metadata. Storage errors have stable codes and a correlation operation ID;
successful creation logs only run ID/operation ID/revision to stderr, no protocol contents.
Application records are bounded; no log files or observability infrastructure. Console access
logs from the local development server are not a durable audit trail.

## Verification and deferred work

Run `ruff check .` and `pytest` (88 passing tests after the Russian UX correction). Tests cover schema validation,
hashes/immutability, creation,
history, transaction rollback, process restart, database settings/failure modes, Git metadata,
shared application services, CLI, Flask form/details/diagnostics, localhost/CSRF/escaping and
dependency boundaries. No Selenium/Playwright package is installed.

Step 2 is **not** included: no acquisition, sources, corpus, BM25, models, evidence, questions,
tasks, scheduler execution, research loop, convergence, reporting, PDFs, scoring or cloud.
Resource ceilings are declarations, not enforcement for future computation. Actual host
admission checks and metering belong to the future evaluated-run entry point.

## Русский интерфейс prototype UI

Навигация: **Исследования → Новое исследование → Диагностика**. Это только сохранение
исследовательской сессии: анализ рынка и модели ещё не подключены. Переключателя языков
и отдельного i18n framework нет. Внутренние поля и CLI остаются английскими.

- **Исходная идея** — опишите замысел обычными словами.
- **Что именно мы исследуем** — нейтральное описание и границы, без «хорошая/плохая».
  Пока задаётся вручную; Idea Parser не реализован.
- **Конфигурация продукта** — конкретная версия продукта, а не весь класс устройств.
- **Рынок / география** — страна, регион или рынок.
- **Для кого предназначен продукт** — предполагаемые пользователи или покупатели.
- **Языки источников** — коды через запятую: `en, de, ru`.
- **Горизонт исследования** — период или глубина прогноза, например ближайшие 5 лет.
- **Использовать источники не позднее** — необязательная историческая граница публикаций.
  Это не дата завершения исследования. Для текущего исследования оставьте пустым.
  Поле использует календарь `type=date`; в Protocol сохраняется ISO-дата или null.
- **Явные предположения** — временные условия, не доказанные факты, по одному на строку.

### Что нужно установить

В обычном поле пишите понятные описания по одному на строку, например:

```text
Время работы от батареи
Диапазон цены
Стоимость ремонта
Существующие альтернативы
```

Web adapter сохраняет каждую непустую строку дословно в `description` (включая пробелы
внутри строки и по краям), с типом `text` и единицей `text`. Внутренние имена — `output_1`,
`output_2` и т.д. Пустые строки пропускаются. Порядок детерминирован; имена из расширенного
поля пропускаются при нумерации, чтобы не было коллизий. Одинаковые описания допускаются
как разные показатели с уникальными именами. Символ `|` в обычном поле — обычный текст.
Сохранённые Protocol и хеши не пересчитываются при отображении и не изменяются локализацией.

В **Расширенных настройках показателей** доступен прежний typed syntax:
`prototype_cost|number|EUR|Стоимость прототипа`. Эти строки добавляются к обычным вопросам.
Можно заполнить только расширенное поле. Укажите уникальное ASCII-имя и поддерживаемую
единицу; числовой показатель не подразумевает бизнес-оценки.

### Необязательные технические настройки

**Явные ограничения** — только явно заданные границы, а не мнение программы. По умолчанию
их нет (`[]`). JSON находится в закрытом блоке **Расширенные настройки / для разработчика**.
Набор вопросов и его версия (playbook) — в **Расширенных настройках исследования**.
Custom Policy JSON — в **Расширенных настройках для разработчика**. Обычный пользователь
не обязан заполнять ни одно из этих полей. Введённые расширенные значения остаются раскрытыми
после ошибки, чтобы их можно было исправить.

### Детали, ошибки и диагностика

Страница исследования показывает описания вопросов, происхождение ограничений и объяснения
версии/политики. `UNVALIDATED` означает непроверенную методологию, а не плохую идею.
Ревизия — неизменяемая версия Protocol/Policy; Manifest — технический паспорт её окружения.
Хеши и идентификаторы доступны в **Технических деталях**, точные значения — в
**Показать исходный JSON**. Лимиты отображаются в GiB/MiB и часах/минутах без изменения Policy.
Округление размера применяется только для показа; исходный JSON сохраняет точное число байт.

Ошибки формы показывают русские названия известных полей и подсказки. Исходный код ошибки,
operation ID и техническое сообщение находятся в раскрывающемся блоке. Ввод не логируется.
Диагностика использует прежний application service и неизменные diagnostic keys; названия,
состояния и размеры переводятся только в представлении. Host/CSRF-защита остаётся включённой.
