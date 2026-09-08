# Simple idea input v0.1

Этот этап — внешний вход, не Evidence Graph/Step 4 и не автоматическое исследование.
На `/research/new` достаточно одной непустой фразы. Кнопка «Исследовать» создаёт
Research CREATED, не запускает collectors, модель или analysis. Необязательные
уточнения скрыты в «Уточнить исследование». Старый полный workflow сохранён по
`/research/new/advanced`; CLI полного Protocol не меняется.

## Boundary

`SimpleIdeaInput v0.1` → `OptionalClarifications` → pure `build_protocol`
(`simple-explicit-v2`) → immutable `ProtocolBuild v0.1` → strict `ResearchProtocol v0.1`
→ существующий ResearchService. Flask только переводит поля формы в input JSON.
Внутренний Protocol не сделан optional и не изменён. Existing corpus/proposal adapters
используются без изменения. Нет ML parser, profile/history, network или cloud calls.

Build хранит exact input, canonical input hash, exact Protocol/hash, builder/schema
versions и per-field origin. `USER_SUPPLIED`, `NOT_SUPPLIED`, `SYSTEM_GENERATED` —
типизированные значения provenance, а не факты. Никаких inferred scope fields пока нет.
Blank optional scalar нормализуется в null, пустые списки в (); различие между
пустой формой и невведённым полем намеренно не сохраняется. Непустой original idea
сохраняется дословно, включая начальные/конечные пробелы.

## Required Protocol fields

Неуказанные neutral_description/product_scope/geography/population получают явный
совместимый sentinel `UNKNOWN (NOT_SUPPLIED)`, languages — `UNKNOWN`; nullable
horizon/cutoff остаются null. Эти placeholders не являются словами пользователя.
Даже если пользователь сам написал текст `UNKNOWN (NOT_SUPPLIED)`, origin остаётся
USER_SUPPLIED: значение и происхождение различимы в build artifact.

Обязательный key output — явно SYSTEM_GENERATED `research_questions`: вопросы для
уточнения scope и необходимых свидетельств. Это начальное направление, не фиктивный
спрос/бюджет/вывод. Будущий playbook может заменить/расширить его явной ревизией.
Additional questions становятся отдельными USER input-derived text outputs.
Бюджет и другие ограничения сохраняются дословно только в input/build с
`USER_SUPPLIED` origin и отдельным mapping status `DEFERRED_NOT_MAPPED`.
Они не становятся key outputs или constraints. Отсутствующие поля имеют
`NOT_SUPPLIED`, явно спроецированные уточнения — `MAPPED`. Provenance и mapping
различаются. Валюта, знак сравнения, единицы и числовой смысл не угадываются.
Для числовых машинно-интерпретируемых constraints пока нужен advanced Protocol.

## Neutralization limitation

`neutralization=NOT_PERFORMED`: arbitrary original idea не копируется в neutral scope.
Так эмоциональная оценка не становится research fact или model-visible instruction.
При одной фразе тема видна человеку в original idea, но автоматический semantic scope
ещё UNKNOWN. Это создание сессии, не семантический разбор идеи. Пользователь может
необязательно указать neutral description/configuration. Эти явные уточнения считаются
scope data, не evidence; existing proposal prompt safety сохраняется. Более сложный
Idea Parser сознательно отложен, без ненадёжного blacklist эмоциональных слов.

## Persistence and compatibility

Additive migration 4 добавляет только `input_builds`, FK на research revision и
immutable UPDATE/DELETE triggers. Build и Research/Protocol/Revision/Manifest пишутся
в одной транзакции; ошибка записи build откатывает всё создание. Build hash и
детерминированный v2 mapping перепроверяются при чтении. Legacy v1 читается с проверкой
hashes, без повторного построения или переписывания старого artifact. Старые исследования не получают
поддельный input artifact; отсутствие строки означает legacy/advanced creation.
Artifact привязан к конкретной исходной ревизии и не переносится при revise.

Все старые Protocol v0.1, policies, corpus snapshots, proposal v1/v2/v3 и reviews
сохраняются без изменения схем объектов/JSON/hashes. На рабочей БД schema 3 → 4
проверена с побайтным сравнением всех старых строк; backup оставлен локально.

## Verification

Regression coverage: one-line creation, blank optional fields, explicit Australia,
budget/questions/assumptions, date, literal sentinel with USER origin, emotional input
kept only in audit, deterministic build/hashes, restart, immutable build, atomic rollback,
simple UI and existing advanced tests. Existing Step 1–3 tests remain in suite.

Browser smoke: только «Двухэкранный ноутбук» создало Research
`771db5ab-d3a3-4a52-9888-9bba718195b7`; details показывают missing fields NOT_SUPPLIED,
нейтральный scope UNKNOWN и SYSTEM_GENERATED initial output. Никакая модель не вызвана.

Build hash: `82b3d800e3aa8b99e6c91a5004c906e762a51e051a516c7f189517227641471f`.
Protocol hash: `1bd7329e4e871478df39093f185dbfa2c820a9eb3dd55313f3584bade11c6d4a`.

Первый smoke выявил strict tuple normalization issue для пустых optional списков;
исправлено до commit. Отдельных Python dependencies не добавлено.

Итог: Ruff PASS, 191 tests PASS, wheel build/isolated install и pip check PASS.
После полного restart browser details/audit показали тот же build hash и Protocol.

Hardening v2: 193 tests PASS (включая Step 1–3), Ruff PASS. Budget `200 AUD`
и exact user constraints сохраняются с USER_SUPPLIED / DEFERRED_NOT_MAPPED после
restart. Protocol содержит только research_questions (и явно заданные дополнительные
вопросы), constraints пуст. Новая migration не добавлялась; legacy v1 canonical bytes
сохранены. Старый smoke выше относится к builder v1.
