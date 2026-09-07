# IAAI Architecture v0.1 — proposal, round 2

Статус: **READY FOR VERTICAL-SLICE IMPLEMENTATION DISCUSSION / NOT FORMALLY ACCEPTED**.
Дата: 2026-09-07. Только архитектурная документация; реализация и ADR не начаты.
Этот раунд заменяет предыдущие рекомендации о первом slice и калибровке.
Связанные документы: [аудит](architecture-review-v0.1.md),
[точный vertical slice и experiment](vertical-slice-v0.1.md),
[реестр policies и параметров](research-policy-v0.1.md).

## Accepted candidate principles

Достаточно устойчивы для Architecture v0.1: scoped convergence и stop certificate;
разделение observations/assertions/evidence/assessments; общий corpus и challenge
obligations; lineage на уровне measurements; SQLite WAL, FULL, один logical writer,
leases/fencing/idempotency; append-only knowledge history; ports/adapters без plugin
framework; локальный бесплатный human-assisted experiment до масштабирования.

«Candidate» фиксирует предварительное согласие пользователя, а не принятие ADR.
Новая причина уточнения: формальная детерминированность сама по себе не делает
бизнес-порог объективным. Любая boundary требует происхождения и scope.
Human review также не может легализовать произвольный aggregate verdict.

## Experimental / calibration parameters

Числа не являются архитектурными инвариантами. ResearchPolicy содержит immutable
SchedulerPolicy, StopPolicy, ResourcePolicy, RuntimePolicy и EvaluationPolicy.
[Полный реестр](research-policy-v0.1.md) задаёт единицы, диапазоны, назначение и способ
калибровки. Старые 40/3, W=3, .05, 6/2/2 и формула 4/2/2 остаются только профилем
advanced-experimental; Phase 1 использует простую policy. Все defaults маркируются
UNVALIDATED; ни число, ни красивый confidence score не становятся научным результатом.

Архитектурные invariants: происхождение constraint, замкнутость provenance,
неповышение истины нормализацией, отсутствие write в core от модели, атомарность
meaningful operation, непротиворечивые budget reservations, отсутствие fabricated
convergence. Калибровка не вправе их отключать.

## 1. Protocol, KeyOutput, Constraint и Assessment

ResearchProtocol = original idea + neutral IdeaSpec + configuration/scenarios +
population/segment + geography + time + languages + playbook/version + output list +
constraint list + policy refs. Эмоциональное framing не попадает в downstream prompts;
содержательные условия сохраняются. Новый сегмент — новая Scenario. Missing scope
явно provisional; нельзя молча подставить предположение, делающее вывод удобным.

KeyOutput — измерение или исследовательский вопрос, а не красная/зелёная категория:

| Поле | Значение |
| --- | --- |
| id / question_ref | Стабильная идентичность и вопрос |
| quantity / predicate | Измеряемая величина либо точное утверждение |
| scope | Configuration, population, geography, period, workload |
| value | Estimate/interval/distribution/category или UNKNOWN |
| unit / denominator | Валюта и base date, на единицу/период/пользователя и т.д. |
| method / input_refs | Измерение или опубликованная formula с provenance |
| evidence_assessment_ref | Достаточность evidence, отдельно от business interpretation |
| comparison_tolerance_ref | Только methodological change detection; может отсутствовать |

Constraint = id, kind, predicate/operator, value/unit, scope, provenance,
assumptions, validity period, verification state, version и supersedes.
Допустимые kinds:

| Категория | Пример | Право на interpretation |
| --- | --- | --- |
| A: Measurement / KeyOutput | prototype cost €42k–€58k | Само по себе не «дорого» |
| B: Evidence-backed constraint | Подтверждённая supplier minimum order | Только в границах контракта/источника |
| C: User-provided constraint | Явный бюджет ≤€20k | Сравнение со stated budget, не универсальная экономическая оценка |
| D: Regulatory/physical/technical boundary | Применимое ограничение/предел при условиях | Evidence/rule refs и проверка применимости обязательны |
| E: Methodological threshold | Допуск изменения оценки между revisions | Только scheduler/stability; запрещён переход к бизнес-вердикту |
| F: Subjective preference | «Предпочитаю меньше конкурентов» | Только явно введённое пользователем preference, отдельно от evidence |

A не subtype Constraint; таблица показывает разные роли данных. B и D могут
перекрываться по происхождению: хранить origin_type отдельно от constraint_kind.
Заявленный physical limit требует условий; manufacturer specification не physical law.
User preference не повышает истинность и не превращается в объективный «рынок плох».

Два независимых результата: EvidenceAssessment(assertion) и
ConstraintEvaluation(output, constraint). Второй имеет SATISFIED_WITHIN_ASSUMPTIONS,
VIOLATED_WITHIN_ASSUMPTIONS, UNDETERMINED, NOT_APPLICABLE; первый — достаточность
поддержки assertion. Violation бюджета не означает CONTRADICTED evidence о стоимости.

Пример interval arithmetic: cost=[42000,58000] EUR и upper budget=20000 EUR при
одинаковых scope/date/cost inclusion → lower(cost)>budget → «оценка стоимости
текущей конфигурации превышает указанный бюджет». Если интервалы перекрываются →
UNDETERMINED. Если нет constraint → вывести interval, не «слишком дорого».
Market size, competitor count, payback аналогичны. Missing comparison tolerance
не разрешает LLM придумать boundary: continuous materiality остаётся unknown,
scheduler использует coverage/exploration. Число конкурентов без temporal dataset
не даёт RAPIDLY_INCREASING или HIGH_COMPETITION.

## 2. Commercial synthesis: только узкие выводы из правил

Phase 1 **не содержит aggregate commercial conclusion**. Report показывает measurements,
scoped evidence assessments, explicit constraint evaluations, conflicts и unknowns.

Позднее допустимы детерминированные conditional inferences:
бюджет нарушен; margin negative во всём обоснованном interval при данной модели;
необходимое technical condition несовместимо с configuration; отсутствует feasible
solution в явно заданном наборе ограничений. Нельзя путать cost и revenue с разными
единицами/горизонтами, складывать зависимые интервалы как независимые или принимать
один supplier quote за универсальную нижнюю границу.

Нельзя: «рынок мал → не стоит делать», «много конкурентов → плохо», большинство
красных категорий → failure, «incumbents не сделали → невозможно», отсутствие
counterevidence → supported business. Даже все constraints satisfied не доказывают
коммерческую жизнеспособность: модель может не включать важный constraint.

Aggregate rule, если появится, хранит target definition, scenario, necessary/sufficient
conditions, input assessments, assumptions, constraint refs, formula/version и
counterevidence. Формулировка «в рамках модели M, при A/B/C, требование X нарушено»
предпочтительнее «данные преимущественно против». Последняя допустима лишь когда
«преимущественно» определено rule и валидировано; сейчас такой модели нет.

Любая смена premise, lineage, scope, correction или нового material counterexample
помечает downstream inference STALE, открывает challenge и требует recomputation.
Старая revision остаётся неизменной. Conditional conclusion всегда показывает
assumptions, диапазон применимости и наблюдение, которое её опровергнет.

## 3. Domain objects и graph

Сохраняются SourceObservation, ExtractionArtifact/Chunk, Assertion,
NormalizedAssertion, Hypothesis, EvidenceLink, DerivedMetric, Inference, Assessment,
Conflict, Gap/Unknown, ResearchQuestion, Task, Entity/EntityLink, ResearchRevision.
Source identity отделена от immutable observation; текстовые offsets — от text hash.
EvidenceLink связывает точный span с конкретным scoped assertion.
Hypothesis/counterclaim — роли assertions; normalization не выдаёт статус FACT.

Assessment states: UNASSESSED, SUPPORTED_WITHIN_SCOPE, CONTRADICTED_WITHIN_SCOPE,
MIXED, INSUFFICIENT_EVIDENCE, NOT_TESTABLE_AS_STATED. Отдельно lifecycle
SUPERSEDED/RETRACTED и coverage/freshness/reviewer state.

Типизированный relational graph с depends_on, addresses, supports, contradicts,
alternative_to, derived_from, cites, supersedes. Provenance/inference dependencies —
DAG immutable inputs; circular self-support запрещён. Question graph может иметь
циклы ссылок, но ссылки не запускают повторную работу автоматически.
Traversal deduplicates outputs и uses visited sets; число путей не число evidence.

Phase 1 использует typed records/validated JSON в SQLite, без универсальной graph
платформы. Relations и provenance не теряются из-за упрощения таблиц.

## 4. Общий evidence ledger, challenges и lineage

Каждый material assertion имеет obligations: neutral inquiry, supporting evidence,
strongest counterexample, alternative explanation, discriminating/falsifying test.
Это intents общей очереди и views общего corpus. Relation assessor не получает
ожидаемую сторону поиска. Relation = supports/contradicts/context_only/not_applicable/
uncertain; NLI neutral не AGAINST. Scope/date/workload mismatch проверяется прежде
чем записывается Conflict. Предпочтение пользователя не используется как label.

Challenge debt считается по assertion+scope+evidence fingerprint и type obligation.
Выполненный challenge не повторяется из-за того, что тезис всё ещё «сильный».
Новые independent evidence, premise correction или scope change делают reopening.
Cooldown предотвращает повтор одной и той же попытки, но не блокирует новый
материальный факт. Баланс процедурный; evidence counts не обязаны быть равны.

Lineage records: copied-from, cites, same-measurement, same-dataset, possibly-dependent.
Группировка на уровне measurement/assertion; dataset/funding dependence хранятся
раздельно и могут пересекаться. 50 копий press release дают один origin, не 50.
Unknown independence → conservative grouped sensitivity, а не произведение score.
Role-specific authority: specs, prevalence, causal study и existence of complaint
требуют разных оснований; единого source_quality нет.

Opportunity anomaly остаётся: prerequisites observed demand/feasibility/economics +
apparently absent supply создают CANDIDATE при adequate coverage.
Проверяются failed products, willingness-to-pay, absolute demand, manufacturing,
BOM/margin, certification, warranty/support, patents, channels, substitutes, liability,
cannibalization и geography. EXPLAINED_WITHIN_SCOPE требует evidence механизма;
PREMISE_REJECTED и UNRESOLVED_ANOMALY допустимы. Отсутствие найденного объяснения
не даёт право приписать incumbents некомпетентность.

## 5. Materiality, unknown unknowns и interactions

Materiality относится к изменению measurement, evidence assessment или применимого
constraint evaluation. Threshold типа E только определяет существенное изменение
исследовательского результата; он не сортирует идеи на хорошие и плохие.

Для reachable KeyOutput вычислить scenario sensitivity по explicit input intervals.
Материальность true если возможные ответы меняют evidence status, constraint outcome
или output больше methodological tolerance. Unknown range/inference → M_UNKNOWN,
не M=0. Указать исходные assumptions, scope и evaluated outputs; никакой оценки
«мне кажется важным» от LLM.

Exploration не ограничивается текущим dependency graph:
coverage matrix и playbook families; seeded sample неиспользованных corpus documents/
source families; anomalies (необъяснённые измерения, units, scope mismatches);
unlinked valid candidate questions. Question proposer видит конкретный source span,
а admission проверяет testable predicate и scope, даже без existing KeyOutput.
Программа создаёт provisional output/gap для таких вопросов и сохраняет их origin.
Одна новая entity без проверяемого вопроса не оправдывает branch.
Нет гарантии обнаружения неизвестного неизвестного; sweep — проверяемая процедура.

Interactions Phase 1: для каждой имеющейся formula/constraint собрать input pairs,
которые входят в одно произведение, отношение, min/max или boundary predicate;
проверить joint interval corners. Например price×volume может пересечь явный
revenue requirement, хотя ни один single-factor scenario этого не делает.
Для monotone rule corners дают bounds; для nonmonotone rule — только sampled sensitivity,
с отметкой unresolved interaction, не доказанная граница.

Число pair tests ограничивает policy. Среди structural pairs часть выбирается FIFO,
часть seeded random из оставшихся, включая individually insensitive factors.
Не строить полный Cartesian product и не ограничиваться «чувствительными» парами:
это пропустило бы именно запрошенный случай. Зависимые входы требуют feasible joint
scenarios; невозможные комбинации исключаются с причиной. Higher-order и no-formula
interactions остаются ledger gaps/exploration hypotheses. Непроверенные material
pairs не дают full-coverage certificate.

## 6. Scheduler: simple first, advanced experimental

Simple Phase 1: deterministic round-robin трёх lanes:
obligation/exploitation, oldest eligible FIFO, exploration. Внутри obligation lane
сначала applicable critical conflict/constraint gap, затем FIFO; никаких weighted
yield forecasts. Reserved exploration и FIFO shares задаются policy.
Baseline A получает те же lanes/slots, но static questions; B может добавлять
dynamic obligations. Uniform exploration документов доступна обеим arms.

Admission events: initial playbook; validated source gap/counterexample; unmet
coverage cell; unlinked testable candidate; applicable anomaly; interaction test.
Reopening: new independent source/premise, corrected span/lineage, changed constraint/
scope или вновь доступный blocked input. Не «прошёл ещё один round».
Deferred сохраняет first_eligible_at; promotion использует возраст и reserved lane.
Aging действует и на deferred, иначе bounded frontier просто скрывает starvation.

Exact fingerprint dedup, proposed-child cap, frontier capacity, graph/resource cap.
Semantic duplicates только candidates на equivalence; misleading merge reversible.
Все capacity refusals имеют reason; material deferred не исчезают из stop gates.
No runnable task without dependencies, lease и reservation. Per-task deadline и
finite retries ограничивают время удержания lane. В finite eligible set FIFO
обслуживает старые элементы; при поступлении новых гарантии ограничены admission
и конечным budget, оставшиеся перечисляются в report.

Advanced policy — optional experiment: sensitivity M, uncertainty U, conflict C,
distinct downstream D, coverage G, calibrated yield Y и normalized cost c.
Формула и коэффициенты только из SchedulerPolicy; источник каждого feature записан.
Сравнить advanced с simple и FIFO на frozen corpus при одинаковых discovery rules,
reviewer/resources/seeds. Primary criterion — material evidence/gap recall per budget,
а не число выполненных tasks. Если нет reproducible benefit, simple остаётся default.

Diagnostics: question ID, admission/reopen event, lane, age (active time и dispatches),
deferred duration, feature vector/score если применим, dependencies, resource estimate,
reservation/actual cost, yield estimate source, challenge fingerprint и rejected reason.

## 7. Convergence: обязательные gates и измеряемые signals

Lifecycle ACTIVE/WAITING/STOPPED отдельно от stop_reason:
CONVERGED_WITHIN_SCOPE, STALLED_INSUFFICIENT_COVERAGE,
INCOMPLETE_RESOURCE_LIMIT, PAUSED_USER, FAILED_SYSTEM.
Provider retry waiting — WAITING, не немедленный terminal failure. При исчерпании
доступных acquisition pathways → STALLED с reason PROVIDER_UNAVAILABLE.
Corruption/невозможность доверять state → FAILED_SYSTEM независимо от budget;
при целостном state cap имеет приоритет над convergence. PAUSED сохраняет resume point.

Обязательные logical gates:
- coherent committed revision, intact provenance;
- no unresolved runnable/deferred critical obligation и pending critical human review;
- material conflict resolved либо explicitly bounded unresolved;
- coverage satisfied либо individually justified unavailable с bounded impact;
- structured report signature stable, low measured novelty;
- выполнены challenge/exploration sweep и interaction obligations;
- отсутствуют unresolved provider/extraction failures, выдаваемые за evidence absence.

Bounded UNKNOWN требует question scope, attempted pathways, reason unavailable,
impact и reopen trigger. Blanket «всё недоступно» не достаточен. Если основной
исследовательский scope не покрыт, STALLED даже при красивом UNKNOWN списке.
Certificate может завершиться insufficient assessment, но не strong verdict через gaps.

Continuous signals: material-new-item count, independent-origin yield, coverage
fraction по eligible cells, output interval delta, premise/lineage turnover,
critical debt, provider success rate, duplicate fraction, age непроверенного frontier.
Для novelty использовать долю новых independent observations, давших хотя бы один
validated material update (0..1); количество updates/observation хранить отдельно.
Это исправляет старое N, у которого numerator мог превышать denominator.
Failed fetch и copied observations не увеличивают знаменатель.

StopPolicy задаёт window, min distinct observations, novelty ceiling и per-output
tolerances. Окно состоит из неперекрывающихся informative batches; нельзя повторно
засчитать тот же пустой round. Frozen finite corpus: отдельный exhaustion path —
все eligible observations рассмотрены и все applicable obligations проверены;
не имитировать W новых rounds. Если substantive coverage не хватает даже после
исчерпания — STALLED. Стабильность prose не используется.

Signature: outputs/assessments/constraints, intervals, assumptions, material
unknowns/conflicts и evidence fingerprints. Material replacement evidence сбрасывает
window, даже если label прежний. Logical gates не заменяются aggregate score.

| Наблюдаемая ситуация | Решение |
| --- | --- |
| Healthy acquisitions, independent exposure, low novelty, gates complete | Candidate scoped saturation |
| Повторяются те же hits, нет независимого exposure | Coverage gap; не saturation |
| Errors/timeouts/known fixture failure | Provider health issue; WAITING, затем STALLED |
| Scope cells растут быстрее покрытия / отсутствуют целые families | SCOPE_TOO_BROAD в certificate; STALLED или resource limit |
| Достигнут cap раньше gates | INCOMPLETE_RESOURCE_LIMIT, остаток frontier |

Scope не сужается молча ради convergence. Новый agreed scope = new protocol/revision.
После convergence новое evidence, correction, changed policy/constraint, reopened
source или applicable freshness condition создаёт child revision с parent ID,
reuse unchanged artifacts, invalidation downstream и новой window. Старый certificate
не переписывается. Нет обязательного фонового мониторинга в Phase 1.

False-convergence tests: late material counterexample, duplicates flood, provider
failure, low extraction yield, unsatisfied coverage, unreviewed critical claim,
deferred material branch, pair-only effect, repeated empty rounds и scope growth.
Новый counterexample после stop должен reopen child revision.

## 8. Persistence, history и resources

SQLite WAL, foreign keys, synchronous=FULL; один coordinator writer, short transactions,
bounded busy timeout, checkpoint, consistent backup; WAL не backup. Local disk,
проверка SQLite/FTS5 capability перед запуском. Tables/typed JSON для protocol,
revisions, tasks/attempts, source artifacts, evidence/graph, operations/events,
reviews и resource ledger. FTS — rebuildable.

Task states PENDING/RUNNING/DONE/FAILED_RETRYABLE/FAILED_FINAL/
BLOCKED_DEPENDENCY/CANCELLED. Lease owner+expiry+fencing generation защищают от
worker, ожившего после sleep. Commit проверяет token; UNIQUE operation key =
kind+immutable inputs+producer/config/schema hashes. Attempts append-only.
Operation outputs+edges+accounting+event+DONE фиксируются атомарно. Network/model
work вне write transaction; fetch at-least-once, local outputs idempotent.
Retry имеет bounded backoff, deadline и budget, а не infinite repair.

Normalized text хранится в SQLite для первого slice; raw temp отдельно.
Crash before commit repeats work; after commit reuses recorded output.
Resource reservation учитывает CPU/tokens/bytes/RAM/disk/WAL/commit reserve,
невозможность persist после hard disk full приводит к recovery последнего durable state.
Counters не сбрасываются resume. Budgets численные только из ResourcePolicy.
Истёкший reviewer budget в experiment тоже cap: непросмотренное не считается validated.

Immutable observations/assertions/assessments + revisions, supersedes/retracts;
recorded_at/revision_seq для «что знали», source_date/retrieved_at отдельно,
valid_from/to только при основании. Late old source не появляется в old report.
Полная bitemporal query engine не нужна.

Hardware Phase 1: один coordinator, sequential tasks, один model subprocess, CPU
baseline на 32 GB RAM; network ограничен corpus preparation. Нет одновременно пяти
моделей. Memory/deadlines задаются policy; Windows spawn, worker restart после fault.
GPU 4 GB optional после реального compatibility/memory test. Для future parallel
варианта bounded asyncio I/O, extraction subprocess и один writer достаточны;
не обещать throughput или необходимые библиотеки до hardware smoke test.

## 9. Acquisition, retention, ports и reproducibility

Phase 1 acquisition: import URL list/normalized artifact и direct URL fetch при
подготовке corpus. FrozenCorpus.lookup(query)/read(ref) — экспериментальный доступ;
general web search не обязателен. Никакого paid endpoint или crawler.
Open machine-readable adapter добавляется только под конкретный источник.

Ports появляются для Acquisition, TextExtractor, ProposalModel и ResearchStore.
Core импортирует domain/ports; adapters реализуют ports, composition root их выбирает.
Result schema: typed data + input refs + producer/config version + diagnostics +
error/abstention. Модель не исполняет инструменты и не устанавливает truth/stop state.
Schema/span/IDs/units validators не гарантируют semantic correctness: reviewer
остаётся ответственным за critical relation/scope в эксперименте.

Retain normalized text+context, source metadata/redirects, raw hash при fetch,
text hash, exact spans, extraction version/warnings. Raw удаляется после committed
validated extraction и по bounded cache policy; failed extraction даёт gap.
Для manual normalized import original hash может быть unavailable, нельзя подделывать.
Tiny разрешённые fixtures отдельно от runtime cache. PDF archive не создаётся.
Audit replay строит report offline; module replay использует saved normalized input;
refresh создаёт новую revision; extraction replay unavailable без тех же raw bytes.
[Manifest и retention Phase 1](vertical-slice-v0.1.md) задают конкретную границу.

Entity resolution пока explicit aliases/IDs + reviewer possible-match; no automatic
fuzzy merge. Mentions сохраняются; correction entity links invalidates downstream.
Fine-tuning, embeddings, NER и NLI не входят в Phase 1.

## 10. Report и diagnostics

Canonical JSON + deterministic Markdown. Measurement, evidence status и constraint
evaluation раздельны; каждая строка с scope, assumptions, for/against evidence,
independence, metrics, unknowns/conflicts, invalidation condition и exact span links.
No aggregate commercial verdict. Отчёт включает stop certificate и review/intervention
summary. Источник source text не является инструкцией приложению.

CLI plan: explain statement-id; show evidence-link/source-span; why scheduled;
why stopped; show conflicts/unknowns; replay operation-id; compare outputs.
Это будущие команды, не реализованная функциональность. Events компактны:
operation/task/attempt IDs, input/output refs, versions, times/resources, reason codes.
Нет chain-of-thought, token streams или giant logs.
Offline report replay byte-stable при pinned renderer; module replay может отличаться
из-за модели/runtime, поэтому сохраняются exact old outputs.

## 11. Architecture readiness

Фундаментального архитектурного blocker для первого vertical slice больше нет.
Можно начать реализацию после отдельного указания пользователя. Не нужно заранее
доказать лучшую priority formula или выбрать пять моделей.
Перед измерением эффекта обязательны frozen protocol/corpus/policies, hidden evaluation
labels и проверка proposal model на pilot: это execution gates эксперимента, не повод
строить новую архитектуру. Phase 1 не доказывает автономный open-web research:
он проверяет controlled human-assisted recursion. Полезность и калибровка остаются
экспериментальными, окончательное принятие Architecture v0.1 — после обсуждения.
