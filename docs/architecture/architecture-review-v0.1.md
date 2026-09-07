# IAAI: критический архитектурный аудит v0.1

Статус: **Architecture v0.1 — ACCEPTED FOR EXPERIMENTAL IMPLEMENTATION**.
Дата: 2026-09-07. Исторические формулировки раундов ниже сохранены как журнал аудита.
Методология experimental, calibration UNVALIDATED, Phase 1 human-assisted;
эффективность recursion требует A/B experiment, concrete models заменяемы.
Основание: пользовательское задание и текущий foundation репозитория.
Продуктовый код не реализован. Этот аудит не подтверждает эффективность методологии:
её ещё необходимо проверить экспериментом.

## Round 2: уточнения после обсуждения

Предварительно принятые принципы сохраняются; их актуальная формулировка находится
в разделе Accepted candidate principles [proposal](architecture-v0.1-proposal.md).
Первый раунд ниже остаётся журналом рисков, а не альтернативной спецификацией slice.
Новые решения второго раунда:

- KeyOutput, ConstraintEvaluation и EvidenceAssessment разделены. Methodological
  threshold не может стать business boundary; manual review не разрешает скрытый score.
- Общий commercial verdict исключён из Phase 1. Узкие comparisons с явно заданным
  constraint допустимы, «слишком дорого» без основания — нет.
- Все tunable defaults вынесены в [versioned policy registry](research-policy-v0.1.md).
  Advanced weighted scheduler отложен; Phase 1 использует SIMPLE/FIFO/exploration.
- Exploration имеет вход вне existing KeyOutputs; pair tests включают individually
  insensitive factors. Это исправляет пробел первого materiality алгоритма.
- Novelty теперь доля независимых observations с обновлением; старое updates/observation
  могло быть больше 1. Frozen exhaustion не создаёт фиктивных пустых rounds.
- Human semantic corrections допустимы только в явно human-assisted stratum;
  ручная генерация ветвей и изменение stop/priority делают run exploratory.
- Один кейс в Phase 1; три и более — Phase 2. Frozen corpus отделяет методологию
  от качества поисковой инфраструктуры. Одна proposal model, без NLI/embeddings/NER.
- A/B сравнивает пакет recursion+challenge с сильным static baseline; все resource
  и reviewer расходы учитываются. Самостоятельный вклад recursion требует ablation.

Точный план: [vertical-slice-v0.1.md](vertical-slice-v0.1.md).
Фундаментального блокера для первого implementation нет; thresholds, полезность
рекурсии и возможная автономность остаются экспериментальными. ADR не принимаются.

## 1. Архитектура, как она понята

IAAI должна превращать идею с явными границами в проверяемый набор вопросов,
собирать реальные источники, извлекать утверждения, проверять конкурирующие
объяснения, расширять исследование и формировать отчёт с воспроизводимыми ссылками.
Цель — обоснованная картина в заданном scope, а не инвестиционное решение или score.
Рекурсия — управляемое пополнение очереди вопросов; она не требует рекурсивных
вызовов программы, отдельных агентов для каждой стороны или микросервисов.

Правильная основа: разделение evidence и inference; критическая проверка обеих
сторон; независимость core от провайдеров; локальная persistence; диагностика
от вывода до фрагмента; бесплатный MVP; benchmark до масштабирования.
Однако ни большое число источников, ни отсутствие новых слов, ни стабильный
текст отчёта не устанавливают истинность и полноту исследования.

## 2. Критические находки

| Риск | Как ломается система | Предложение |
| --- | --- | --- |
| Неограниченная convergence | Интернет и пространство вопросов не перечислимы; каждый UNKNOWN порождает ещё вопросы | Только `CONVERGED_WITHIN_SCOPE`, с coverage certificate и границами; отдельный ресурсный исход |
| «NORMALIZED_FACT» | Нормализация придаёт утверждению незаслуженный статус истины | `NormalizedAssertion`, преобразования отдельно от evidence assessment |
| Две стороны как независимые агенты | Каждая ищет подтверждение собственной позиции; 50 перепечаток побеждают один эксперимент | Общий корпус, нейтральные вопросы, challenge obligations, lineage и проверяемые tests |
| Самый сильный вывод всегда следующий | Один устойчивый тезис бесконечно вытесняет остальные | Challenge debt, cooldown, бюджет исследования альтернатив и aging |
| Автоматическое признание UNKNOWN | Закрытие трудных вопросов создаёт искусственную сходимость | UNKNOWN с причиной, журналом попыток, последствиями и условием reopening |
| Симметрия количества evidence | Отсутствие опровержения считается поддержкой, вводится false balance | Критическая проверка симметрична процедурно, evidence не обязана быть 50/50 |
| NLI как truth engine | Entailment пересказа ложного источника выглядит как истина | NLI только предлагает отношение passage→claim; пригодность источника проверяется отдельно |
| Удаление всех оригиналов | Ошибки таблиц, OCR и контекста нельзя воспроизвести; повторная загрузка даёт другие байты | Разделить downstream replay и extraction replay; сохранять нормализованный контекст, честно маркировать потерю оригинала |
| SQLite WAL = неуязвимость | Неподходящий sync, длинные readers, заполнение диска, повреждение носителя | FULL, короткие транзакции, резерв, online backup, crash tests; WAL не backup |
| stale RUNNING→PENDING | Старый worker возвращается после sleep и пишет второй результат | Lease + fencing token + уникальный operation key + атомарный commit |
| «ML confidence» как вероятность | Некалиброванный score превращается в псевдоточность вывода | Раздельные score, applicability и uncertainty; abstention, калибровка на своих данных |
| Evidence absence | Поиск не обнаружил конкурентов — отчёт утверждает отсутствие | Search coverage ledger; закрытый перечень требует доказанной полноты |
| €0 search | Бесплатный endpoint недоступен, rate-limited или нерелевантен географии | Manual URL/search import как полноценный адаптер, явные пробелы, без обхода ограничений |
| Независимость провайдеров на бумаге | Универсальный интерфейс протекает токенизатором, SQL и vendor scores | Семантические контракты и conformance fixtures, отдельные capability descriptors |
| Утечки и prompt injection | Веб-страница велит модели менять scope, читать файлы или выдать секрет | Источники только данные; модель не исполняет инструменты; сеть и пути проверяет приложение |

## 3. Недоопределённые основания

Нужен `ResearchProtocol`: конфигурация продукта, регион, период, сегмент, единицы,
исследовательские выходы и границы допустимой генерализации. «Перспективность» и
«жизнеспособность» не являются атомарными проверяемыми claim. До оценки экономики
нужны горизонт, сценарий объёма, BOM, цена, каналы, warranty, распределение затрат.
Если границы не заданы, система показывает варианты и предположения; она не выбирает
наиболее удобный сегмент незаметно для пользователя.

Playbooks полезны как версии наборов вопросов и требований к evidence, а не как
фиксированная онтология отраслей. Один вопрос может происходить из нескольких
playbooks. Применимость и исключения фиксируются. Dynamic branch допускается
при наличии конкретного gap, contradicting observation или проверяемого механизма.
Новая сущность сама по себе недостаточна для расширения графа.

«Другой сегмент спасает идею» — альтернативная конфигурация, а не опровержение
вывода о текущей конфигурации. «Квадратное колесо» требует выяснить геометрию пути,
подвеску и ограничения эксплуатации. Абсурдность формулировки не является evidence.

## 4. Что сократить в MVP

Один application coordinator, один SQLite adapter, обычные таблицы графа,
один model worker, CLI и статический Markdown/JSON report. Сначала нет необходимости
в отдельном graph database, vector DB, DuckDB, message broker, plugin marketplace,
общем agent framework, UI Inspector, event-sourcing framework, полной bitemporal БД,
пяти одновременно установленных моделях или fine-tuning.

NER не обязателен, чтобы проверить методологию. Reranker и embeddings добавляются
только сравнением с BM25 baseline. Первая диагностика — команды просмотра
provenance и компактный JSON export. Model runtime не должен становиться новой
универсальной платформой: достаточно процесса с несколькими типизированными операциями.

## 5. Аномалия незанятой возможности

Триггер — не «нет конкурентов», а совместная рабочая гипотеза: подтверждённые в scope
спрос, реализуемость, экономика, релевантные incumbents и низкое наблюдаемое предложение.
Каждая предпосылка имеет собственный assessment; слабая coverage делает аномалию
предварительной. Система создаёт один deduplicated `OpportunityAnomaly` с ссылками
на предпосылки, альтернативы и tests, а не готовое объяснение.

Обязательный checklist: платёжеспособность и абсолютный размер рынка; эксперименты
и закрытые продукты; substitutes; производство/BOM/margin; сертификация; support и
warranty; patents; liability; каналы; cannibalization; география; ошибки измерения.
Наличие патента само по себе не доказывает запрет или коммерческую неосуществимость.
История неудачного продукта не доказывает универсальный запрет на будущую версию.

Состояния: `CANDIDATE → INVESTIGATING → EXPLAINED_WITHIN_SCOPE`,
`PREMISE_REJECTED` или `UNRESOLVED_ANOMALY`. Объяснение требует evidence механизма и
проверки альтернатив. Оно не выводится из предположения о рациональности incumbents.
При отсутствии объяснения аномалия остаётся видимой и ослабляет основание для
коммерческого synthesis. Она не обязана запрещать остановку всего исследования.

## 6. ML: роли и пределы

| Компонент | Допустимая роль | Ограничение / baseline |
| --- | --- | --- |
| Small Qwen-class | Предложить IdeaSpec, claims и вопросы в схеме | Генерация не evidence; проверка ссылок и единиц кодом; bounded repair, затем abstain |
| multilingual E5-small-class | Multilingual candidate retrieval | Не source authority; проверить prefixes/token limits конкретного adapter; сначала BM25 |
| GLiNER-class | Предложить entity spans | Не entity resolution; отложить до измеренного entity bottleneck |
| mDeBERTa/XNLI-class | passage–claim relation candidate | Neutral не AGAINST; числа, scope и causal validity требуют отдельных проверок |
| BGE-style reranker | Пересортировать небольшой union кандидатов | Может выкинуть редкое опровержение; измерять recall по независимым группам |

У Qwen и NLI частично перекрывается classification; у Qwen и GLiNER — entity extraction.
Это альтернативы для ablation, не обязательные последовательные стадии.
Генеративной модели нельзя поручать арифметику как единственный механизм, назначение
истины, credentials, транзакции, правила остановки, выполнение загруженного кода,
необратимое entity merge или самостоятельное утверждение causal inference.

Детерминированными должны быть hashing, ссылки/span validation, units, formulas,
graph admission, provenance integrity, task lifecycle, resource accounting, scheduler,
convergence и сборка отчёта. Это не устраняет субъективность protocol: правила и
пороги должны быть опубликованы, версионированы и проверены на sensitivity.

## 7. Ограничения и основания внешних утверждений

Ниже первичные источники, проверенные 2026-09-07. Численные пороги в proposal —
наши стартовые экспериментальные настройки, а не результат этих публикаций.

- [SQLite WAL](https://www.sqlite.org/wal.html): readers могут работать с writer,
  но одновременно writer только один; WAL требует совместной памяти на одном host.
- [SQLite synchronous](https://sqlite.org/pragma.html#pragma_synchronous): FULL
  синхронизирует WAL при commit; NORMAL допускает потерю последних committed
  транзакций при power failure. Физическую надёжность накопителя это не гарантирует.
- [SQLite FTS5](https://www.sqlite.org/fts5.html): доступен BM25; его score нужно
  интерпретировать с правильным направлением сортировки.
- [E5 model card](https://huggingface.co/intfloat/multilingual-e5-small): кандидат
  multilingual embeddings; применимость к корпусу IAAI требует отдельной оценки.
- [mDeBERTa model card](https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-mnli-xnli):
  NLI training не подтверждает достоверность научных или коммерческих выводов IAAI.
- [GLiNER paper](https://aclanthology.org/2024.naacl-long.300/): open-type extraction
  сущностей; разрешение идентичности остаётся отдельной задачей.
- [Qwen model card](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct): пример small
  local candidate, без выбора его архитектурной зависимостью.
- [NVIDIA legacy GPU table](https://developer.nvidia.com/cuda/gpus/legacy) и
  [Pascal compatibility guide](https://docs.nvidia.com/cuda/pdf/Pascal_Compatibility_Guide.pdf):
  legacy hardware требует проверки runtime compatibility. 4 GB из задания принимаются
  как бюджет ноутбука; характеристики desktop P2000 не подменяют измерение этого GPU.

## 8. Решение, которое предлагается обсудить

Принять только экспериментальный протокол и ограничения первого vertical slice из
[Architecture v0.1 proposal](architecture-v0.1-proposal.md), затем проверить на реальных
источниках, улучшает ли рекурсивная критическая проверка качество относительно
фиксированного playbook при равном бюджете. Если не улучшает — упростить методологию.
Ни один ADR и ни одна окончательная архитектура этим аудитом не принимаются.
