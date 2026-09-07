# Phase 1 / Step 2 — источники, фиксированный корпус и BM25

Step 1 принят и объединён в PR #2. Step 2 добавляет только подготовку корпуса и лексический
поиск. Нет LLM, аналитических выводов, Evidence Graph, Research Loop или оценок бизнеса.

## Пользовательский путь

Запустите `iaai serve`, откройте исследование → **Источники и корпус**.

1. **Загрузить источник** — публичный HTML URL, который разрешено использовать.
2. Или **Импортировать текст вручную** — текст, инициатор, при наличии название, URL и
   известная дата публикации. Неизвестные данные оставьте пустыми.
3. Откройте источник, проверьте текст, предупреждения и точные фрагменты.
4. Включите нужные материалы в рабочий корпус; можно исключать и добавлять материалы.
5. **Зафиксировать корпус** — создаётся неизменяемый снимок состава.
6. В снимке: **Поиск по корпусу → Открыть фрагмент**. Выделяется точный сохранённый текст,
   доступен полный окружающий контекст. Поиск не оценивает достоверность источника.

Следующая фиксация создаёт новую версию. Старый снимок и поиск доступны после перезапуска.

## Domain / границы

- Source — идентичность URL или ручного ресурса, не скачанный текст.
- SourceObservation — конкретное получение: новый ID/timestamp даже при одинаковых байтах,
  URL/redirect chain, HTTP status/type, raw SHA-256, размер, adapter version, инициатор и config.
- ExtractionArtifact — immutable text/hash, metadata и их происхождение, encoding,
  extractor version, warnings/status. Unknown metadata не выдумывается.
- TextChunk — artifact ID/text hash, start/end, exact text/chunk hash, chunking version.
- Corpus — рабочий редактируемый набор artifact IDs конкретного Research.
- CorpusSnapshot — неизменяемые refs/hashes, Research revision/Protocol hash, config,
  index runtime и envelope с ID/version/timestamp/инициатором.

Application использует Acquisition, CorpusStore, Retriever ports. ResearchStore сохраняет
прежний контракт. Composition root выбирает HTTP/SQLite/FTS5 и inject-ит функции extraction/
chunking. UI/CLI вызывают один CorpusService. Нет Flask/urllib3/bs4 в domain/application,
нет SQL в UI. Новые сущности не подменяют прежние ResearchRevision/RunManifest.

## Конфигурация и совместимость

`corpus-policy-v0.2.json` — отдельный строго валидируемый CorpusPolicy для операций Step 2,
а не переписанная ResearchPolicy v0.1. Resolved config сохраняется в каждой Observation и
CorpusSnapshot. Все defaults UNVALIDATED. Старые Protocol/Policy/Revision/Manifest JSON и
хеши не изменяются. Такой вариант не навязывает новые поля историческим Step 1 runs.

Начальные лимиты: connect 10 с, read 15 с, проверяемый deadline 60 с, response 2 MiB,
5 redirects, raw cache 512 MiB / TTL 1 час, normalized text 2 млн символов, chunk 1200,
корпус 100 артефактов / 20 млн символов, query 500 символов / 20 результатов. Это не полный
Resource Ledger. Web-форма дополнительно ограничена прежними 256 KiB всего запроса;
для более крупного разрешённого текста используйте CLI.

## HTTP acquisition / безопасность

urllib3 предоставляет готовый HTTP/TLS stack, потоковое чтение, timeouts и pinned-IP
соединение с исходным TLS SNI/hostname verification. Собственный HTTP stack не написан.

- Только HTTP(S), стандартные порты 80/443; credentials, control chars, backslash, zone IDs
  и file URLs отвергаются. Host IDNA/lowercase, fragment удаляется. Path/query сохраняются,
  tracking-параметры не удаляются, query не сортируется.
- DNS проверяется перед каждым переходом. Все ответы должны быть public; private, loopback,
  link-local, multicast, reserved/unspecified и mapped/tunnel IPv6 блокируются. Соединение
  выполняется по выбранному числовому IP: между проверкой и соединением нет повторного
  разрешения hostname, которое могло бы вернуть другой IP при DNS rebinding.
- Проверка каждого redirect; автоматические redirects/retries отключены. Нет browser cookies,
  auth, пользовательских headers, proxy environment или выполнения инструкций из HTML.
- TLS verification включена, используется системный trust store Python.
- Размер проверяется по Content-Length и потоково. Запрашивается identity encoding;
  compressed responses явно не поддерживаются, чтобы исключить decompression bombs.

Это **не абсолютная SSRF-гарантия**: доверяем OS resolver/маршрутизации/TLS trust store.
Синхронный DNS resolver подчиняется таймаутам ОС, а не Python deadline. Deadline проверяется
между сетевыми операциями и может быть превышен на один connect/read timeout. Нет watchdog
или отдельного network sandbox/egress firewall. HTTP без TLS не доказывает подлинность.
Нет обхода логина, paywall, CAPTCHA или ограничений доступа; нет crawler/general search.

PDF/binary → UNSUPPORTED_MEDIA_TYPE с сохранённой Observation, без PDF parsing/OCR.
Прерванный/oversized response не получает hash полного файла: body/raw_hash отсутствуют,
byte_count отражает только прочитанный префикс (или 0 при отказе по Content-Length).

## Extraction / exact spans

Beautiful Soup + stdlib html.parser восстанавливают обычный malformed HTML. Кодировка
выбирается по HTTP hint, HTML metadata и доступным fallback; encoding/replacement warnings
сохраняются. Удаляются script/style/noscript/template, nav/footer/forms/iframe/SVG/canvas,
явно hidden элементы. Block boundaries → переводы строк, entities декодируются, whitespace
нормализуется. Это не идеальное boilerplate removal. HTML никогда не рендерится в UI.

Title/author/publication date берутся только из явно присутствующих HTML fields. ISO date/
timestamp валидируется. Это **metadata издателя**, не независимая проверка. Language unknown.
Явно JS-only/требующая JavaScript страница получает INCOMPLETE и не включается в корпус.
Все static extractions предупреждают, что полнота не гарантируется; распознать все
динамические страницы без выполнения JavaScript невозможно.

Manual import помечен HUMAN_IMPORTED, metadata HUMAN_SUPPLIED, raw_hash отсутствует;
raw extraction replay unavailable. Исходный файл не сохраняется. Импорт — не HTML extraction.

Chunking `block-char-v1`: последовательные окна не длиннее chunk_chars, по возможности до
перевода строки, без overlap. Offsets — Python Unicode code points, полуинтервал `[start,end)`,
не UTF-8 bytes/UTF-16 units. Проверяется `artifact.text[start:end] == chunk.text`.
Изменение chunk config требует нового импорта/artifact и нового snapshot; старые chunks
не перегенерируются. Полный normalized text доступен как surrounding context.

## Persistence / raw lifecycle

Migration 2 добавляет sources, observations, artifacts, chunks, corpus_members,
corpus_snapshots, raw_cache, cache_events. V1 структура проверяется до upgrade, v2 — после;
DDL/version транзакционны. WAL/FULL/FK остаются. Immutable records защищены UPDATE/DELETE
triggers. Нет task/graph/evidence таблиц. Проверена миграция на копии реальной Step 1 DB.

Raw HTML временно хранится в SQLite BLOB cache в локальной runtime-папке. До extraction
тело stage-ится с общей квотой payload bytes. После durable commit observation/artifact/chunks
очистка по TTL разрешена и регистрируется в cache_events. До commit raw не удаляется.
Failed extraction сохраняет FAILED artifact, raw удерживается до TTL. Это не web archive.

Cleanup ленивый: при URL fetch и doctor/diagnostics, не фоновый scheduler. При crash между
staging и commit pending raw не удаляется автоматически; diagnostics показывает pending count,
квота при заполнении блокирует новые staging operations. Это консервативное удержание
неподтверждённых данных, не task recovery framework. Квота не ограничивает полный SQLite/WAL
файл; DELETE не означает secure erase или немедленное уменьшение файла. Permanent state —
normalized text, provenance, hashes, chunks. Перед рабочей миграцией создан SQLite backup.

## Corpus / cutoff / duplicates

Включение в draft — явный выбор, не подтверждение истины. FAILED/UNSUPPORTED/INCOMPLETE
недопустимы. Known publication date позже source_cutoff → OUTSIDE_SOURCE_CUTOFF.
retrieved_at не заменяет дату публикации. Unknown date допустима с SOURCE_DATE_UNKNOWN.
Freeze повторно проверяет cutoff и неизменность draft/Research revision во время подготовки.

CorpusContent содержит sorted artifact refs, artifact/text/chunk hashes, Research revision/
Protocol hash, полный config и index runtime. corpus_hash — SHA-256 его canonical JSON.
Snapshot ID/version/timestamp/инициатор — envelope, не входят в corpus_hash. Поэтому одинаковый
resolved content даёт тот же corpus_hash и новый snapshot ID/version. Общий content_hash
Snapshot включает envelope. Изменение состава, artifact, chunk config или SQLite version
меняет corpus identity. Старые snapshots остаются доступны и не мутируют.

Raw hash, text hash и URL identity — разные понятия. UI показывает кандидатов в текстовые
дубликаты, но не делает выводов о независимости авторов/измерений. Lineage Engine отложен.

## BM25 / FTS5

Поддержка проверяется созданием FTS5 virtual table, не по версии Python. Индекс — rebuildable
**in-memory projection выбранного snapshot**, собирается при каждом запросе из проверенных
chunks. Посторонние документы не влияют на IDF/avgdl. Это baseline для небольших корпусов.
FTS5 unavailable → typed FTS5_UNAVAILABLE; import/corpus/freeze работают, fallback нет.

Unicode61 tokenizer; BM25 SQLite (k1=1.2, b=0.75 — семантика FTS5). Query words экранируются
как literals и соединяются OR; произвольный FTS query language не исполняется. Сортировка
score ASC — более отрицательный score лучше; tie-break — canonical insertion order.
Результаты содержат snapshot/hash/query/rank/score, chunk/source/artifact IDs, offsets,
exact text/preview, index version. Нет русского stemming, embeddings/reranker/truth scores.
Изменившийся SQLite runtime требует нового snapshot для поиска; старые записи читаются.

## CLI

```text
iaai source add-url RESEARCH_ID https://example.com/
iaai source import-text RESEARCH_ID --file source.txt --title "Название" --initiated-by "Автор"
iaai source list RESEARCH_ID
iaai source show ARTIFACT_ID
iaai corpus include RESEARCH_ID ARTIFACT_ID
iaai corpus exclude RESEARCH_ID ARTIFACT_ID
iaai corpus show RESEARCH_ID
iaai corpus freeze RESEARCH_ID
iaai corpus search SNAPSHOT_ID "battery life"
iaai doctor
```

CLI --file — разрешённый ручной импорт, не file:// и не доступ веб-источника к файловой системе.
UI и CLI используют один service. Интернет не обязателен для doctor и локального поиска.

## Dependencies / verification / deferred

Новые direct runtime dependencies: urllib3 >=2.6,<3 (HTTP/TLS/streaming/pinned IP) и
beautifulsoup4 >=4.14,<5 (HTML/encoding/recovery). Transitive soupsieve; typing-extensions уже
была установлена. Новых dev dependencies нет. Не нужны headless browser/ML/ORM/PDF tools.

Tests используют собственные HTML fixtures и fake resolver/transport/acquisition, CI без
внешнего интернета. Покрыты v1 migration, hashes/Unicode spans, raw lifecycle, SSRF redirects/
DNS/TLS pinning, limits, freeze/BM25 scope/rank, FTS failure, UI/CLI/security и boundaries.
Реальный public URL — отдельный локальный smoke, не CI.

Локальная приёмка 2026-09-08: Ruff PASS, 133 tests PASS, wheel build/install и
packaged config/templates/FTS5 PASS, pip check PASS. На копии и рабочей Step 1 DB
миграция 1 → 2 сохранила прежние JSON/хеши побайтно (4 Protocol, 1 Policy,
4 Research, 4 Revision, 4 Manifest). Browser smoke: https://example.com/ → FETCHED /
EXTRACTED; отдельный собственный manual text → HUMAN_IMPORTED; два artifacts → freeze →
query `battery` → exact highlighted chunk. После остановки/запуска сервера тот же
snapshot/hash/chunk/rank/score сохранились. Демонстрационные данные находятся только
в ignored runtime DB и не являются выводами исследования.

Вне Step 2: general search/crawler, PDF/OCR, LLM, assertions/evidence, full lineage,
tasks/scheduler, recursion, convergence, scoring и аналитические отчёты.

Primary references: [urllib3 custom SNI](https://urllib3.readthedocs.io/en/stable/advanced-usage.html#custom-sni-hostname),
[SQLite FTS5/BM25](https://www.sqlite.org/fts5.html#the_bm25_function),
[Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/bs4/doc/).
