# Vertical slice v0.1: конкретный первый эксперимент

Статус: **implementation-ready candidate**, 2026-09-07; код ещё не пишется.
Главная гипотеза: recursive challenge-driven research находит больше существенных
evidence/gaps/counterexamples при сопоставимых ресурсах, чем fixed playbook.
Ссылки: [proposal](architecture-v0.1-proposal.md), [policies](research-policy-v0.1.md).

## 1. Phase 0 — manual/frozen methodology validation

Один кейс: dual-screen laptop для явно заданного рабочего сценария в Австралии.
До run зафиксировать configuration, workload (два активных экрана, document/browser
работа), сегмент и дату источников. KeyOutputs: reported battery measurements,
price/cost scope, repair/warranty conditions, comparable alternatives и evidence
о потребности/WTP. Отсутствие публичных WTP данных → UNKNOWN, не поиск заменяющего
его search-demand score. User budget не придумывать. Можно отдельно иметь synthetic
constraint fixture для тестирования арифметики, помеченный не пользовательским вводом.

Curator вручную составляет real-source corpus около 20 документов (ориентир 15–25):
official product/spec/warranty pages; independent workload-based reviews;
Australian public consumer guidance где применимо; user observations с ограничением
«существование сообщения», не prevalence. Источники конкретно отбираются и даты
проверяются при подготовке experiment, здесь никаких неподтверждённых claims о рынке.
Разные editorial URLs с одним measurement считаются одной independence group.

Curator делает initial playbook около 6 scoped questions и hidden reference labels:
spans, counterevidence, scope conflicts, plausible missing questions. Manual walkthrough
проверяет, различимы ли outcomes A/B и можно ли написать rule/coverage certificate.
Все ручные branches размечаются; Phase 0 ничего не доказывает об автоматизации.
Если корпус не содержит полезных discriminating evidence, это failure dataset design,
а не неудача IAAI. Curator не дополняет corpus после просмотра результатов B.

## 2. Phase 1 — один настоящий end-to-end кейс

Три кейса сразу избыточны для первого implementation. B2B и square-wheel scenario
переходят в Phase 2. Точный состав Phase 1:

| Компонент | Решение |
| --- | --- |
| Protocol/KeyOutput/Constraint | Typed schema, validation, immutable revisions; scope вводит человек до run |
| Store + task runner | SQLite WAL/FULL, один logical writer; tasks/attempts, lease/fencing, idempotency |
| Acquisition preparation | Manual URL list + direct fetch allowlisted public HTTP(S); persisted normalized import |
| General web search / crawler | Не нужен; evaluated run на frozen corpus |
| Open machine-readable sources | Import text/JSON supported; отдельный provider только если требуется выбранным corpus |
| HTML extraction | Да: text/spans/metadata, unsupported content→gap; без JavaScript browser crawler |
| PDF parsing / OCR | Нет; если важный source только PDF, pre-run ручной normalized import с intervention provenance или scope gap |
| BM25 | Да, corpus-only retrieval, versioned chunking; raw corpus доступен только через metered retrieval/read |
| Local LLM | Одна small generative proposal model в одном процессе; explicit abstention |
| Model tasks | Candidate claims + source-grounded gap/question proposals; neutral IdeaSpec уже фиксирован |
| Evidence relation | System proposal optional из той же модели; critical relation всегда reviewer-validated |
| NLI / embeddings / reranker / NER | Нет |
| Entity linking | Explicit IDs/aliases и possible_match review, без fuzzy auto-merge |
| Graph + simple scheduler | Typed edges, three lanes, bounded frontier/deferred, admission/reopening |
| Challenges / recursion | В B обязательны system-generated child question из observed gap, без обязательного числа удачных branches |
| Metrics / synthesis | Deterministic scoped outputs и explicit constraint comparisons; no aggregate commercial verdict |
| Stop engine | Logical gates, policy signals, finite-corpus exhaustion и отдельные incomplete/stalled outcomes |
| Report / diagnostics | JSON + Markdown, CLI explain/replay, bounded operation events |

Нет требования скачать весь corpus за каждую arm: preparation общая, одинаковая;
но evidence exposure каждой arm отдельно учитывает bytes/tokens read. Нельзя дать B
весь текст в prompt бесплатно и считать только новые fetches. Candidate retrieval,
read, proposal generation, failed attempts и review входят в budgets.

Implementation order после отдельного поручения:

1. Protocol/policy/manifest validation и revision store; один сохранённый source/span.
2. URL/import/fetch + HTML extraction + hash/span validation, frozen corpus и BM25.
3. Одна proposal model с exact input/output capture и abstention; reviewer queue.
4. Assertion/evidence/lineage graph; scoped deterministic metrics и fixed-playbook A.
5. Simple scheduler + dynamic gap/challenge admission B; recursive continuation.
6. Stop certificate, report renderer, explain/why/replay commands.
7. Crash/reopen/invariance fixtures; paired run и structured comparison A/B.

Не строить инфраструктуру наперёд: после каждого шага сохранить runnable artifact;
после шага 4 уже можно увидеть качество extraction/review. Невозможность получить
полезные proposals в hardware pilot — измеренный bottleneck, не повод добавить ещё
четыре модели. Можно выполнить deterministic template-only ablation, но он проверяет
только заданный класс gaps; claims о general dynamic discovery будут ограничены.

## 3. Одна модель: максимальная польза от proposals

Primary role: source-grounded candidate claim extraction и gap/question proposals.
Для каждой candidate: exact input span IDs, scoped predicate, evidence needed,
reason code (scope mismatch/missing measurement/alternative/contradiction), parent
question. Deterministic validators проверяют IDs/spans/schema/units, но не истинность
semantic link. Reviewer подтверждает critical extraction/relation. Модель может
abstain; результат UNKNOWN валиднее fabricated observation.

Необходимые runtime capabilities: локальный запуск, bounded context, structured
outputs, cancellable invocation, fixed model/tokenizer digest и recorded settings.
Бренд не выбирается как architectural dependency. Та же модель может предложить
relation, но это не независимый evaluator. Idea parsing в Phase 1 manual pre-run:
нет необходимости расходовать модель на уже фиксированный scope.

Без LLM возможна Phase 0 и rule-based narrow Phase 1 ablation. Human-authored dynamic
questions не заменяют программу в primary Phase 1. Если local model не даёт валидных
questions после заранее ограниченного pilot, run фиксирует failure/abstention;
нельзя незаметно заменить её человеком и заявить успех метода.

## 4. Human boundary

Программа обязательно ведёт protocol/revision, acquisition/import records, extraction,
retrieval, proposals, graph, lanes, challenge debt, recursion, deterministic metrics,
stop decision, provenance и renderer. Reviewer не выбирает следующую ветку.

Разрешено подтвердить/исправить critical extracted claim, evidence relation, ambiguity
scope/lineage. Исправление обязано опираться на уже предъявленный exact context.
Reviewer не читает hidden gold и не выполняет внешние поиски во время оценённого run.
Одинаковый review rubric в A/B, reviewer по возможности blinded к arm.

Intervention record: run/operation ID, reviewer ID, action type, before/after refs,
source refs, reason, active seconds, timestamp, criticality, arm visibility и
whether procedural intervention. Types: ACCEPT, REJECT, EDIT_CLAIM, EDIT_RELATION,
ADJUDICATE_SCOPE, ADJUDICATE_LINEAGE; отдельно ADD_BRANCH, ADD_SOURCE, OVERRIDE_PRIORITY,
OVERRIDE_STOP, CHANGE_SCOPE, GOLD_LEAK.

Последние шесть делают run ineligible для primary controlled-methodology comparison;
сохранить его как exploratory, а не удалить результаты. STOP ради безопасности
не нарушение, но run incomplete. Непредусмотренный бюджетный extension, помощь одной
arm или ручная «наводка» proposer также protocol deviation. Pre-run одинаковая
corpus curation допустима; post-run независимое scoring не feeding подсказок.

Даже чистый primary run с semantic corrections — **human-assisted methodology test**,
не полностью autonomous. Отдельная fully autonomous stratum требует zero semantic
interventions во время run; offline scoring после завершения допустимо.
Показывать system-original и reviewed outcomes отдельно. Если существенное evidence
появилось только после EDIT_CLAIM/RELATION, credit=review-assisted. Новая идея reviewer,
даже вставленная в поле correction, считается ADD_BRANCH и protocol deviation.

Reviewer effort: active seconds total/per accepted material item, accepts/rejects/edits,
edit magnitude, pending critical queue, interventions per operation, system-origin vs
review-assisted discoveries. Большое число исправлений само по себе не скрывает run,
но ограничивает утверждение об automation. Reviewer-budget exhaustion оставляет
unreviewed critical items и INCOMPLETE_RESOURCE_LIMIT, не автоматически DONE.

## 5. Честный A/B experiment

Primary estimand: эффект пакета «dynamic gap-driven recursion + challenges» поверх
fixed-playbook при общей evidence/review/report инфраструктуре. Это не изолированный
эффект только recursion; для атрибуции позже нужна ablation.

Arm A: заранее фиксированные вопросы и query variants, same BM25/acquisition, same
evidence rules; может получать FOR/AGAINST из найденного текста и заполнять coverage,
но не добавляет post-observation вопросы. Нейтральные/counterexample templates уже
есть в static playbook, чтобы baseline не был заведомо слабым.
Arm B: те же initial questions + query templates + data, и dynamic gap/challenge
questions после наблюдений. Review pipeline, proposal model/version и relation rubric
одинаковые; B оплачивает дополнительные proposals из своего общего budget.

До run freeze: corpus hash, policies, initial questions, rules, source families,
time/language/scope, model/seeds, hardware conditions, reviewer allowance и metrics.
Нельзя включать gold questions/labels в model prompts или retrieval index. Отдельные
state databases, никакого reuse evaluated evidence из другой arm. Warmup общий и
учтён одинаково; порядок A/B случайный/чередующийся, чтобы memory/thermal/cache и
reviewer learning не помогали всегда одной arm. Повторить зарегистрированные seeds.

Два отчёта сравнения:

- Natural-stop: качество, stop reason и фактические costs каждой arm.
- Budget-matched curves: discoveries при одинаковых заранее заданных budget checkpoints.
  Вектор constraints CPU, active time, bytes read/fetched, model tokens, reviewer time
  одинаков; нет компенсации больших tokens маленьким числом документов без явной policy.
  Если A закончилась раньше, для основной equal-cost comparison взять её checkpoint и
  соответствующий prefix B. Дополнительный результат B сверх затрат A показывается
  отдельно, не как «тот же budget».

Frozen corpus bytes-read считаются при каждом logical read, включая cache hits;
physical disk I/O отдельно. Shared extraction/index construction одинаково и вынесено
в setup ledger. Independent source groups scored unique; 50 copies не 50 discoveries.
Task/query counts диагностические, не reward и не production stopping criterion.
Для same-cost сравнения берутся prefixes, не повторные прогоны с подсмотренными answers.

Primary outcomes: unique gold-matched material evidence и independent counterevidence
recall; critical false assumptions exposed; material gaps обнаружены программой;
unsupported material inference count; reviewer effort и actual resources.
Gold mapping сначала по span/assertion/scope, затем blinded adjudication для novel
valid items, которых не было в gold; одинаковые правила для A/B, не reject novelty
только за отсутствие заранее известного label. Каждое additional item связано с
изменением measurement/assessment/constraint или явно scoped unknown, не business score.

Primary discovery credit требует system-origin question/retrieval и validated evidence;
review-assisted extraction correction отдельно. Report polish и число questions не
метрики успеха. Benefit заявляется только при улучшении material discovery/false
assumptions на matched resources, без роста unsupported statements и без скрытого
reviewer subsidy. При tradeoff показать Pareto outcomes, не сворачивать в score.

## 6. Phase 2 — расширенный benchmark

Добавить B2B software и square-wheel with explicit track, затем приблизительно 12
кейсов разных типов из первого аудита. Разделить dev/held-out по темам, не по
формулировкам одной идеи. Два blinded annotators/adjudication где возможно; при одном
публиковать exploratory limitation. Larger tests отделяют corpus curation bias от
методологии. Один Phase 1 кейс показывает feasibility, не general effectiveness.

Ablations: static+challenge без dynamic questions; dynamic без targeted challenge;
SIMPLE vs FIFO vs ADV с одинаковыми question-generation rules; template-only proposer
vs одна model. General web acquisition оценивается отдельным этапом после frozen
corpus, чтобы provider quality не скрывала methodological effect.

Tests: positive/negative/neutral framing одной scoped идеи; delayed contrary evidence;
syndicated duplicate flood; broken provider; lost extraction; unreviewed critical
claim; same-result different-premise signature; pair-only effects; stale-worker commit;
crash до/после commit; retraction после convergence; offline report rebuild.
Никаких научных заявлений по одному seed или оптимизированному на test порогу.

## 7. Retention и Acquisition v0.1

Минимальный interface, pseudocode only:

    import_urls(urls, provenance) -> source_refs
    import_normalized(text, metadata, provenance) -> artifact_ref
    fetch(source_ref, limits) -> raw_observation | typed_error
    extract(raw_observation) -> artifact | unsupported
    frozen_lookup(query, limits) -> ranked_refs
    read(ref, limits) -> normalized_input

Manual import фиксирует кто/когда и preprocessing. Direct fetch только HTTP(S)
public sources, без credentials, private/local network addresses и unlimited redirects;
source content не команды. SearchProvider universal interface пока не нужен.
Open API adapters будущие, никакого обязательного paid search.

Permanent normalized text, context и exact spans + source URLs/title/dates/author,
lineage, raw hash когда известен, text hash, extractor version/warnings.
Raw cache transient с TTL/byte ceiling из RuntimePolicy; deletion только после
validated artifact commit, кроме aborted unusable download. Cache cleanup event
фиксирует raw availability. Optional tiny разрешённый extraction fixture corpus
ограничен policy и отделён от research sessions; не постоянный PDF archive.

Report replay badges: AUDIT_REPLAY_AVAILABLE, MODULE_REPLAY_AVAILABLE при retained
input; ACQUISITION_REFRESH_IS_NEW_REVISION; EXTRACTION_REPLAY_UNAVAILABLE при удалённом
raw. Missing raw не притворяется exact extraction replay. Manual PDF transcription
может поддержать analysis, но extraction provenance маркируется HUMAN_IMPORTED.

## 8. Manifest v0.1 и diagnostics

Минимальный immutable manifest с referenced blobs сохранёнными и hash-validated:

    manifest_schema_version, run_id, arm, parent_revision_id, revision_seq
    protocol_content + hash, resolved_policy_content + hash
    code_git_commit, dirty_patch_hash_or_clean, dependency/runtime_versions
    corpus_manifest_ref + hash, source/artifact/span hashes, extraction_versions
    model/tokenizer/quantization digests, backend/OS/hardware, seed/settings
    prompt_template_content + version, actual ordered input refs/truncation decisions
    operation_input/output_refs + hashes, review/intervention_ledger_ref
    renderer/schema_version, stop_certificate_ref, resource_ledger_ref

Один hash без доступного содержимого недостаточен. Offline report не использует
current time/network: timestamp берётся из revision, canonical sorting/formatting
и renderer version pinned. Old structured model outputs сохраняются, не только seed.
Module replay создаёт separate output version; comparison показывает additions,
removed spans, label/scope changes и downstream effects, не перезаписывает baseline.
Нет giant prompts/logs/token streams/chain-of-thought: template + exact ordered inputs
позволяют восстановить обычный prompt; truncation/sampling decisions тоже сохранены.

Будущие CLI commands, их назначение и минимальный результат:

| Command | Diagnostic answer |
| --- | --- |
| explain statement-id | Rule/premises, for/against, assumptions, producer operation |
| show evidence-link ID | Relation, reviewer edits, lineage, scope applicability |
| show source-span ID | Exact quote/context/hash и extraction warnings |
| why scheduled question-id | Admission, lane/age/deferred, reason, budget |
| why stopped research-id | Gates/signals, policy, health, open work, certificate |
| show conflicts / show unknowns | Unresolved items, impact, attempted pathways, reopen triggers |
| replay operation-id | Saved normalized input→separate replacement output, no network |
| compare outputs old new | Structured diff + cost + affected assertions |

Metrics и summaries по meaningful operation достаточны. Если неправильный claim
уже в extracted text — extraction; text верен, span/claim неверен — proposer; relation
неверна — model/review; evidence не retrieved — BM25/acquisition; вопрос не admitted —
scheduler; evidence верна, итог неверен — rule/renderer; early stop — gates/policy.
Это диагностика причин по сохранённым inputs, не предположение «виновата LLM».

## 9. Readiness

Да, фундаментальных architectural blockers для Phase 1 нет. Scope frozen-corpus,
human-assisted и один кейс выбраны явно. До benchmark измерения нужно подготовить
и заморозить corpus/rubric/policies и проверить model capability на pilot; это
обычные первые шаги implementation, не нерешённая архитектура. Окончательная полезность
recursion, calibration и автономность должны быть установлены экспериментально.
Продуктовый код начинается только по следующему поручению пользователя.
