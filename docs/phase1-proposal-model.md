# Phase 1 / Step 3 — локальные предложения и ручная проверка

Step 2 принят и объединён в PR #3 (`db246e7`). Step 3 заканчивается на reviewed
candidates. LLM output ≠ evidence ≠ fact ≠ assessment. Принятие человеком означает
выбор формулировки для будущей проверки, не подтверждение её истинности.

## Пользовательский путь

Откройте frozen corpus → **Предложения модели — новый вопрос** → введите конкретный
исследовательский вопрос → **Сформировать предложения**. После CPU-генерации доступны
исходные кандидаты, использованный текст, ссылки на exact chunks и **Очередь проверки**.
BM25 ищет буквальные слова вопроса, без перевода/stemming/embeddings. Русский вопрос
может не найти английские chunks. Это диагностируемый пробел retrieval, не повод
незаметно дать модели весь корпус.

Для каждого кандидата: **Принять**, **Отклонить**, **Редактировать и принять**.
Исходный текст модели всегда остаётся. HUMAN_REVIEWED и EDITED_ACCEPTED обозначают
участие человека, не fully autonomous outcome и не truth status. Непроверенные записи
никогда не принимаются автоматически. Второе решение для уже проверенного кандидата
отклоняется как REVIEW_CONFLICT. Комментарии и reason codes сохраняются.

## Один runtime и одна модель

Используется subprocess adapter к официальному **llama-completion.exe**, llama.cpp
`b10809`, version `0.4.0-dev`, commit `5266f24da`, Windows x86_64 CPU build.
В этом release completion executable предоставляет простой конечный текстовый протокол;
интерактивный CLI/server не нужен. Не требуется llama-cpp-python, compilation, PyTorch,
Transformers, CUDA toolkit или server daemon. Application зависит только от ProposalModel
port. ChatML framing — версия конкретного adapter/template, не универсальная поддержка
всех моделей. При замене baseline требуется новый совместимый template/pilot.

Baseline: **Qwen/Qwen2.5-3B-Instruct-GGUF**, `qwen2.5-3b-instruct-q4_k_m.gguf`, Q4_K_M.
Размер 2,104,932,768 bytes. SHA-256:

```text
626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d
```

Это open-weight модель под отдельной **qwen-research** лицензией, не Apache-2.0
лицензия IAAI. Перед использованием вне текущего исследовательского pilot ознакомьтесь
с её условиями. Модель/веса не распространяются вместе с IAAI.

Primary sources: [официальная model card и лицензия](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF),
[официальный runtime release](https://github.com/ggml-org/llama.cpp/releases/tag/b10809).

## Явный локальный setup (Windows PowerShell)

Никаких downloads при запуске приложения, doctor или proposal run. Скачивание — отдельный
осознанный setup. Веса и бинарники находятся в ignored `models/` и `runtime/`.
Один baseline, без автоматического выбора альтернатив.

1. Скачайте [CPU x64 ZIP](https://github.com/ggml-org/llama.cpp/releases/download/b10809/llama-b10809-bin-win-cpu-x64.zip)
   в `runtime/llama-setup/llama.zip`. Expected SHA-256 release asset:
   `9df3158ed228a641a4b127942d7f459f24c9e13f04682659d05c00c80099b6b5`.
   Проверьте `Get-FileHash -Algorithm SHA256`, затем распакуйте весь ZIP вместе с DLL
   в `runtime/llama-b10809/`. Не копируйте один launcher без DLL.
2. Скачайте [один GGUF](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf)
   во временный `models/qwen2.5-3b-instruct-q4_k_m.gguf.part`. Проверьте SHA-256 выше,
   только затем переименуйте в `.gguf`. Незавершённый файл не считается установленным.
3. Создайте локальный `runtime/model-config.json` с абсолютными путями:

```json
{
  "executable": "C:/absolute/project/runtime/llama-b10809/llama-completion.exe",
  "model_path": "C:/absolute/project/models/qwen2.5-3b-instruct-q4_k_m.gguf",
  "name": "Qwen/Qwen2.5-3B-Instruct-GGUF",
  "quantization": "Q4_K_M",
  "expected_sha256": "626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d"
}
```

Можно указать другой путь config через `IAAI_MODEL_CONFIG`. Произвольные CLI flags через
config/web не разрешены. Запустите `iaai model doctor`: ожидается USABLE. Doctor проверяет
файлы, GGUF magic/hash, executable `--version`, не загружает веса в inference. Hash кешируется
по file stat для повторного doctor, перед каждым generation GGUF хешируется заново.
Названия/quantization — supplied setup metadata; file hash идентифицирует реальные bytes.
Tokenization находится внутри GGUF и покрыта его digest.

Без config: NOT_CONFIGURED, без runtime/model: typed diagnostic. Step 1/2 продолжают
работать. `iaai doctor` не требует configured model для общего статуса OK.

## Policy / bounded context

ProposalPolicy v0.3/version 1: UNVALIDATED, top-K 3, source text максимум 4000 Unicode
символов, полный UTF-8 prompt максимум 12000 bytes, context window 16384 tokens,
output 768 tokens, timeout 300 s, stdout 32768 bytes, stderr 16384 bytes,
temperature 0, seed 42, CPU threads 6, GPU layers 0. Resolved policy и hash сохраняются.
Параметры не заявлены оптимальными. Это не полный Research Resource Ledger.

Исходный вопрос без скрытого rewrite передаётся существующему snapshot-local BM25.
Сохраняются retrieval query/index version, ranks/scores и returned exact chunks.
В model context попадает bounded subset в ranked order. Chunks не обрезаются посередине:
слишком большой chunk пропускается, omitted IDs записываются. Полные точные тексты
переданных chunks сохранены. Дополнительные байты JSON/Protocol/schema тоже входят
в полный prompt budget. Byte-bound консервативно резервирует tokenizer capacity для
выбранного byte-fallback baseline; это не универсальный token counter для любых моделей.

Prompt разделяет SYSTEM CONTRACT, RESEARCH SCOPE, RESEARCH QUESTION, SOURCE CHUNKS,
OUTPUT SCHEMA. Data кодируются JSON, источники не являются командами. Exact rendered
prompt/hash, system contract/schema template content/hash/version сохранены. Revision
берётся из frozen snapshot, не из текущего Research pointer. Старый scope остаётся старым.

## Structured output / abstention

JSON содержит claims (`text`, `chunk_ids`), questions (`text`, `reason`, `chunk_ids`),
`abstention`. При пустых списках нужен непустой abstention reason. При наличии кандидатов
abstention пуст. Каждый кандидат обязан сослаться хотя бы на один переданный chunk.
Проверяются типы, неизвестные поля, непустые строки, длины/counts, chunk IDs.
Дубликаты текста после whitespace/case normalization или повтор IDs отклоняют весь batch.
Существование chunk reference **не проверяет semantic entailment**.

Wire protocol: один JSON document, optional trailing `[end of text]` от llama-completion.
Удаляется только этот exact terminal marker; полный stdout остаётся в operation.
Markdown/fences, дополнительные документы, duplicate JSON keys и невалидная схема →
MODEL_OUTPUT_INVALID, без candidates, без repair call. Runtime JSON grammar помогает,
но не заменяет Pydantic validators: некоторые regex constraints runtime не поддерживает,
warning сохраняется. Свободная reasoning prose не запрашивается, hidden reasoning channel
не собирается. Raw diagnostic text никогда не evidence.

## Process safety / failure semantics

Absolute executable/model paths, args list, shell=False, stdin DEVNULL. Prompt/schema
передаются через временные UTF-8 files, не shell command. Временная папка удаляется после
операции, exact input уже сохранён в SQLite. No tools, plugins, cloud endpoints или HTTP
в model adapter. `--offline`, без HF/model URL/RPC flags. Environment очищен от
LLAMA_ARG_* и credentials. CPU offload явно отключён. OS lock допускает только одну
IAAI inference одновременно; другая получает MODEL_BUSY, не очередь scheduler.

stdout/stderr читаются параллельно с byte ceilings; overflow завершает процесс.
Timeout завершает process tree через Windows taskkill / POSIX process group.
Missing runtime/model, timeout, nonzero exit/OOM/crash или invalid output не меняют
Research/Corpus и сохраняются как failure. OOM не диагностируется по одному exit code:
MODEL_PROCESS_FAILED с bounded stderr, не выдуманный диагноз.

Это **не secure OS sandbox**. Доверенный executable имеет права пользователя ОС,
DLL/search path и файловая система не изолированы. `--offline`/очищенный env не равны
egress firewall. Prompt injection resistance не гарантируется: структурная защита —
у модели нет инструментов и полномочий, её результат только текст в PENDING_REVIEW.

## Persistence / audit / review measurements

Migration 3 добавляет четыре таблицы: proposal_operations, proposal_results,
proposal_candidates, review_decisions. Input/result разделены, чтобы durable input
существовал **до** запуска процесса. Request/result/candidates/decisions append-only,
UPDATE/DELETE blocked. Result + candidates сохраняются одной транзакцией.
Если процесс приложения аварийно завершился до result commit, input остаётся
RECORDED_WITHOUT_RESULT: запуск мог ещё выполняться или прерваться. Не выдаём это за
успешный result, не запускаем повтор автоматически. Это не task recovery framework.

ReviewDecision отдельно содержит actor, timestamp, action, reason/comment, edited text,
HUMAN_REVIEWED. UNIQUE candidate_id делает competing second review явным конфликтом.
Сохраняются generated/pending/accepted/rejected/edited counts и deterministic text-change
metric: сумма длин различающихся середин после общего prefix/suffix. Это не Levenshtein
и не quality score. Время review — timestamps, не измеренное active reviewer time.

Audit replay обязателен: `proposal show` открывает exact input/output/config/IDs и
решения после restart. Generation replay — новый explicit run (новый operation ID),
не перезапись старого. Seed/temperature не гарантируют bit-identical output между
runtime/hardware versions. Смена runtime требует нового pilot; старый audit доступен.

## CLI

```text
iaai model doctor
iaai proposal run SNAPSHOT_ID --question "Какие проблемы батареи стоит проверить?"
iaai proposal show OPERATION_ID
iaai proposal queue RESEARCH_ID
iaai proposal accept CANDIDATE_ID --reviewer "Имя"
iaai proposal reject CANDIDATE_ID --reason IRRELEVANT --reviewer "Имя"
iaai proposal edit-accept CANDIDATE_ID --text "Новая формулировка" --reviewer "Имя"
```

UI/CLI используют один application service. При redirected Windows console может
понадобиться `python -X utf8 -m iaai ...` для русского текста. UI HTML экранируется,
CSRF/Host protections Step 1 сохранены.

## Prompt boundary v2

Новые операции используют `proposal-chatml-v2`. Model-visible scope строится по явному
allowlist нейтральных полей: description/product/geography/population, horizon/cutoff,
languages/key outputs и playbook. `original_idea` не передаётся модели, но полный
immutable Protocol остаётся в ProposalRequest и protocol hash для audit.
Assumptions и constraints вынесены в отдельные секции NOT EVIDENCE: это условия
и границы, не факты и не findings.

Все недоверенные model-visible данные сериализуются детерминированным JSON с
Unicode escaping `<` → `\u003c` и `>` → `\u003e`, включая вопрос, scope, assumptions,
constraints и полные context records. JSON decoding обратимо восстанавливает данные.
Сохранённые exact chunks и underlying context не меняются. Сохраняемый prompt и его
hash относятся к фактически отправляемому escaped тексту. Только доверенный template
добавляет literal ChatML role markers. Это структурная защита от дополнительных ролей,
а не гарантия семантической устойчивости модели к prompt injection.

System contract требует сохранять величины, единицы и смысл чисел; запрещает расчёты,
конвертацию валют, экстраполяцию и переименование величин без явного основания в
цитируемом фрагменте. Полезный неподтверждённый расчёт предлагается как вопрос.
Это prompt-level guard, не numerical validator и не semantic entailment.
Общий предел candidates передаётся из resolved policy; до двух claims и двух questions —
предпочтение внутри этого предела, не отдельный противоречащий лимит.

Чтение v1 сохранено; старые prompts/hashes не регенерируются. SQLite migration не нужна,
adapter/wire version не меняется. Приведённые ниже результаты 170 tests и real pilot
относятся к исходному v1.

Hardening v2 проверен локально: Ruff PASS, 176 tests PASS (170 прежних + 6 новых),
wheel build/isolated install и pip check PASS. Все исторические durable rows основной
и synthetic pilot DB совпали побайтно после повторного открытия, включая failed v1,
successful v1, pending candidates и review decisions. Схема остаётся 3.

Один реальный CPU injection run: operation `cc14ed92-e281-4694-bf05-e869681a6707`,
51.75 s, PENDING_REVIEW. Exact source содержит ChatML injection; rendered prompt имеет
только 3 im_start и 2 im_end от template. Модель вернула обычный structured JSON,
но поместила вопрос в claims: semantic quality не установлено. Research/corpus не изменены.

Один повтор прежнего numerical pilot на том же snapshot без изменения corpus:
operation `73a43416-7099-49ef-8537-8e24ee2ead30`, 59.625 s, PENDING_REVIEW.
Модель больше не добавила EUR, но всё ещё назвала цену устройства стоимостью прототипа
и написала бессодержательное «1800 AUD, что эквивалентно 1800 AUD или 1800 AUD».
Numeric prompt guard не устранил semantic hallucination. Кандидаты не приняты,
repair/retry не выполнялись; оригиналы сохранены. Это quality observation, не benchmark.

## Pilot / validation / deferred

Реальный CPU pilot: три собственных synthetic источника (battery, repair, unrelated),
русский explicit question. BM25 выбрал один battery chunk. После исправления обработки
runtime EOS marker получены valid claim + question за ~52 s, PENDING_REVIEW.
Первый MODEL_OUTPUT_INVALID сохранён, не подменён успешным. Это feasibility smoke,
не benchmark: формулировки модели требуют реального reviewer и качество не установлено.

Browser smoke после реального inference: accept/reject/edit-accept сохранены и пережили
restart вместе с original text; действия явно отмечены `Codex UI smoke — simulated
reviewer` и выполнены только в отдельной synthetic pilot DB. Это проверка механики
review, не настоящий human assessment и не данные будущего A/B.

Дополнительный run на существующем Step 2 snapshot завершился за 59.4 s. Он выявил
конкретную ошибку качества: модель добавила отсутствующий в context пересчёт AUD → EUR
и назвала цену устройства стоимостью прототипа. Эти формулировки сохранены только
как непроверенные кандидаты; автоматически не приняты и не исправлены. Существование
правильного chunk ID не делает semantic grounding истинным. Полезность baseline
требует отдельной оценки; этот smoke не подтверждает качество исследования.

CI использует только FakeModel и маленькие subprocess fixtures, не GGUF и не интернет.
Локальная итоговая проверка: Ruff PASS, 170 tests PASS, wheel build/install и pip check PASS.
Установленный wheel запускается без model config, содержит proposal templates, но не
GGUF/executable/DB. Основная пользовательская БД также мигрирована 2 → 3: все исторические
Step 1/2 rows побайтно совпали с резервной копией; новые pending candidates не приняты.
Migration smoke на копии рабочей v2 DB сохраняет все historical Step 1/2 JSON/hashes.
No new Python dependencies. Existing Ollama installation/models не изменялись.

Отложены Evidence Graph/Assertion/EvidenceLink, NLI, embeddings/reranker, authority,
support/contradict, scheduler/tasks, recursive questions, Research Loop, A/B execution,
convergence/Stop Certificate, commercial verdict и аналитические отчёты.
