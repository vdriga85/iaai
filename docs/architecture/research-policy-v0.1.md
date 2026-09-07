# ResearchPolicy v0.1: architectural rules и calibration

Статус: candidate schema, defaults **UNVALIDATED**. Дата: 2026-09-07.
Это документация; config files и продуктовый код не создаются.

## 1. Чистая model configuration

ResearchProtocol описывает WHAT: scope, output/constraint identities, assumptions.
ResearchPolicy описывает HOW: scheduling, stop, resources, runtime, evaluation.
Business/user constraints никогда не извлекаются из SchedulerPolicy или StopPolicy.

ResearchPolicy = schema_version, policy_id, content_hash, parent_policy_ref,
status (UNVALIDATED/PILOT_CALIBRATED/EVALUATED), calibration_dataset_ref,
SchedulerPolicy_ref, StopPolicy_ref, ResourcePolicy_ref, RuntimePolicy_ref,
EvaluationPolicy_ref. Manifest сохраняет resolved content, не только имя файла.
Каждый nested policy immutable и имеет version/hash. Resolved values фиксируются
до paired run. Изменение даже одного threshold создаёт child policy/revision;
нельзя подбирать параметры на held-out test и затем объявлять его независимым.

Поля числовые строго typed с units; unknown/null отличается от 0. Unknown keys,
NaN, отрицательные budgets, нулевые denominators и incompatible versions запрещены.
Сумма lane shares=1; exploration и FIFO имеют положительный reserve; resource
reservations не превышают host capability. Validation errors останавливают start.
Production run требует конечных resource ceilings; отсутствие business constraint
допустимо и не заменяется нулём/benchmark default.

Policy не может отключить provenance, unit checking, stop integrity, atomicity,
truth/evidence separation или запрет hidden business scoring. Такие изменения —
архитектурный revision, не calibration. Числа ниже — стартовые профили: SIMPLE
для Phase 1, ADV для later ablation. Неиспользуемые ADV поля не влияют на SIMPLE.

## 2. SchedulerPolicy registry

| Parameter / default | Units / допустимый диапазон | Зачем | Калибровка |
| --- | --- | --- | --- |
| mode=SIMPLE | SIMPLE/ADV/FIFO | Сравнивать политики | Paired critical discovery per budget |
| frontier_capacity=40 | questions, integer ≥1 | RAM и graph explosion | Frontier sweep vs omission/deferred wait |
| children_per_proposal=3 | questions, integer ≥1 | Bounded generation | Discovery vs duplicates/token cost |
| lane_shares SIMPLE=1/3,1/3,1/3; ADV=.6,.2,.2 | fractions [0,1], sum=1; FIFO/exploration >0 | Exploit, age, explore | Compare delay/coverage under equal cost |
| exploration_seed=0 | integer 0..2^32−1 | Repeatable sampling | Registered seed list, не выбрать лучший |
| interaction_pair_cap=6 | pairs per output per sweep, integer ≥1 | Bound combinatorics | Pair-only failure cases и omitted interactions |
| interaction_random_share=.5 | fraction (0,1) | Include individually insensitive pairs | Pair coverage vs cost |
| retry_cooldown=30 | active seconds, >0 | Не повторять transient failure немедленно | Failure-injection recovery latency |
| ADV weights M/U/C/D/G=4/2/2/1/1 | nonnegative finite, sum>0 | Explicit priority features | Dev ablation vs SIMPLE/FIFO |
| ADV uncertainty unknown/mixed/stable=1/.5/0 | fractions [0,1], ordered | Explainable feature encoding | Calibrated gap detection, не confidence истины |
| ADV yield_prior=.5 | fraction [0,1] | Cold-start yield | Smoothed independent evidence yield |
| ADV yield_prior_strength=2 | pseudo-observations >0 | Avoid one-hit extremes | Dev reliability of forecasts |
| ADV yield_floor=.25 | fraction (0,1] | Poor history не лишает вопрос всех шансов | Source-family starvation ablation |
| ADV cost_floor=.01 | normalized cost >0 | Avoid divide by zero | Cheap-task flooding tests |
| ADV cost_exponent=.5 | real [0,1] | Control cheap-task preference | Budget matched critical recall |
| ADV CPU/token/byte cost weights=1/3 each | fractions [0,1], sum=1 | Normalize resource dimensions | Pareto costs, sensitivity |

ADV expression: (wM*M+wU*U+wC*C+wD*D+wG*G) ×
(yield_floor+(1-yield_floor)*Y) / max(c,cost_floor)^cost_exponent.
Y=(successes+prior_strength*yield_prior)/(trials+prior_strength), где trial означает
eligible independent acquisition, success — validated material update. Definition
фиксируется schema, values policy. D=log(1+reachable_outputs)/log(1+all_outputs);
если outputs нет, D=0 и M_UNKNOWN уходит в exploration. Evidence fingerprint equality
запрещает повтор завершённого challenge независимо от cooldown; новая evidence
может открыть его сразу. Cycle/task counts не являются stopping condition.

FIFO age измеряется first eligibility, а не временем последнего promotion.
Shares реализуются weighted round-robin без требования именно 10 slots; пустая lane
отдаёт слот следующей runnable. Deferred входит в FIFO promotion. Fairness ограничена
конечным бюджетом; всё не обслуженное отражается в certificate.

## 3. StopPolicy registry

| Parameter / default | Units / допустимый диапазон | Зачем | Калибровка |
| --- | --- | --- | --- |
| informative_window=3 | batches, integer ≥1 | Sustained stability | Hidden late-counterexample tests |
| min_independent_exposure=5 | origins per batch, integer ≥1 | Не принимать пустоту за saturation | Sparse/deduplicated corpora |
| novelty_ceiling=.05 | fraction [0,1] | Low new material yield | False stop vs extra resource curve |
| output_abs_tolerance=null | same unit as output, >0 when defined | Numeric comparison | Measurement resolution + sensitivity; no business judgment |
| output_rel_tolerance=null | fraction (0,1] when defined | Scale-aware delta | Dev interval stability, explicit null for zero-scale |
| freshness_interval=null | seconds >0 or explicit manual-refresh-only | Reopen stale observation | Source update patterns; no background service in Phase 1 |
| required_coverage_cells | finite typed list with applicability reasons | What counts as covered | Protocol review before runs; cannot delete failed cells post hoc |
| provider_health_probe_interval=60 | active seconds >0 | Separate broken provider from exhausted corpus | Inject timeouts/fixture failure |

If both numeric tolerances exist, delta threshold=max(abs_tol, rel_tol*reference_scale),
with scale and interval endpoint rule recorded; absent both means numeric stability
UNASSESSED, not automatic pass. Для Phase 1 outputs с недостающим tolerance выбирают
frozen-corpus exhaustion path с неизменным validated structured output, а не выдуманный
business cutoff. Изменение discrete evidence state/constraint outcome всегда material.
Canonical representation и fingerprints rules — schema, не tunable rounding trick.

Exhaustion path не требует фиктивных W batches: complete corpus scan + all applicable
obligations + no pending material work + stable recomputation; insufficient substantive
coverage всё равно STALLED. Report указывает saturation_path=window/exhaustion.

## 4. ResourcePolicy / RuntimePolicy registry

Budgets ниже действуют одинаково на A/B. Preprocessing/model installation cost отдельно
измеряется и амортизируется поровну; runtime consumption включает неудачные attempts.

| Parameter / default | Units / допустимый диапазон | Зачем | Калибровка |
| --- | --- | --- | --- |
| run_disk=2 GiB; pool_disk=20 GiB | bytes >0, run≤pool≤available | Persistence bound | Measured text/index/WAL peak |
| host_free_reserve=30 GiB | bytes >0, <actual free at start | Save/commit margin | Disk pressure crash test |
| normalized_text=200 MiB; raw_cache=512 MiB | bytes >0 ≤pool | Limit corpus/temp expansion | Parser stress and corpus footprint |
| fetched_bytes=200 MiB per arm | bytes >0 | Equal acquisition allowance | Paired discovery-cost curves |
| CPU=7200; active_elapsed=14400 | seconds >0 | Finite work, hung tasks | Laptop pilot; all process CPU counted |
| wall_deadline=86400 | seconds >0, ≥active limit | Bound sleep/network waits | Resume scenarios; deadline not silently reset |
| generated_tokens=50000 | tokens integer >0 | Bound proposals | Pilot useful proposal/token ratio |
| model_input_tokens=200000 | tokens integer >0 | No free huge-context scans | Measured input workload |
| graph_nodes=5000 | nodes integer >0 ≥frontier | Bound total ledger | Explosion injection |
| reviewer_active=1800 per arm | seconds >0 | Equal human aid | Pilot workload; pauses excluded by logged rule |
| RSS=16 GiB | bytes >0 <host RAM | Leave OS headroom | Peak working set, not weight file size |
| context=2048; output_per_call=512 | tokens >0 within runtime capacity | Bound latency/memory | Span fidelity and truncation tests |
| model_batch=1 | integer ≥1 subject to RSS | Predictable local runtime | CPU baseline; throughput later |
| network_concurrency=1 | integer ≥1 bounded by policy | Minimal fetch setup | Preparation throughput; evaluated runs offline |
| task_timeout=120 | active seconds >0 | Hung process bound | Slow fixture and model pilot |
| transient_attempts=3; schema_repairs=1; OOM_retries=1 | integer ≥1 for attempts, ≥0 for repairs | Finite failure cost | Fault injection; terminal reason retained |
| busy_timeout=5; lease_duration=180; heartbeat=30 | seconds >0, heartbeat<lease; operation deadline<lease initially | Writer/worker recovery | Sleep and stale worker tests |
| WAL_checkpoint_target=16 MiB | bytes >0 below disk reserve | Avoid unbounded WAL | Long-reader stress |
| raw_cache_TTL=3600 | seconds ≥0, purge only after commit/validation | Ephemeral originals | Extraction troubleshooting vs storage |
| extraction_fixture_max=5 MiB | bytes ≥0 (0=disabled) | Tiny reproducible tests | Minimum representative permitted fixtures |

Все defaults предварительные. Unsupported runtime параметр не игнорируется, а
вызывает config validation error. Backoff multiplier=2 и jitter fraction=.2 — tunable
RuntimePolicy (multiplier≥1, jitter [0,1]); calibrate retry storms. One model/one writer
— выбранный Phase 1 process design, не утверждение о максимуме полной системы.
Encoder batches, RRF constant, semantic thresholds отсутствуют в SIMPLE schema:
не добавляем неиспользуемые switches; введение adapter потребует policy revision.

## 5. EvaluationPolicy registry

| Parameter / default | Units / допустимый диапазон | Зачем | Калибровка |
| --- | --- | --- | --- |
| corpus_target=20 (range 15–25) | documents, integer ≥1 | Feasible first experiment | Pilot adequate scope/families; freeze actual count |
| initial_questions_target=6 | questions, integer ≥1 | Comparable starting state | Protocol applicability before evaluation |
| repeat_seeds=[0,1,2] | nonempty distinct integer list | Stochastic variation | More repeats if variance high |
| checkpoint_fractions=[.25,.5,.75,1] | increasing fractions (0,1] | Equal-cost curves | Pre-register; not winning-checkpoint selection |
| retrieval_recall_target=.90 | fraction [0,1] | Diagnostic retrieval gate | Labeled independent groups on dev corpus |
| auto_relation_precision_target=.95 | fraction [0,1] | Future automation only | Confidence intervals on independent evaluation |
| framing_Jaccard_target=.90 | fraction [0,1] | Invariance diagnostic | Topic-family held-out; raw disagreements shown |
| phase2_cases=12; dev_cases=6 | integers total≥2, 0<dev<total | Broader evaluation | Increase based on uncertainty, not fake significance |

Exact source-span resolution, no unmarked human intervention, no unsupported material
statement, no forbidden business verdict — correctness gates, не настраиваемые
проценты «допустимой лжи». Targets .90/.95 не означают достигнутую надёжность.
Confidence interval method и pairing unit pre-registered; один Phase 1 кейс — pilot,
не статистическое доказательство эффективности для всех идей.
