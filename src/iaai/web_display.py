"""Russian presentation helpers only; persisted schemas and values stay unchanged."""

from pydantic import ValidationError

from iaai.errors import IAAIError

FIELD_LABELS = {
    "original_idea": "Исходная идея",
    "neutral_description": "Что именно мы исследуем",
    "product_scope": "Конфигурация продукта",
    "geography": "Рынок / география",
    "target_population": "Для кого предназначен продукт",
    "languages": "Языки источников",
    "time_horizon": "Горизонт исследования",
    "source_cutoff": "Использовать источники не позднее",
    "key_outputs": "Что нужно установить",
    "assumptions": "Явные предположения",
    "constraints": "Явные ограничения",
    "playbook_reference": "Набор исследовательских вопросов",
    "playbook_version": "Версия набора вопросов",
    "name": "Внутренний идентификатор",
    "description": "Описание",
    "value_type": "Тип значения",
    "unit": "Единица измерения",
    "output": "Показатель",
    "type": "Тип ограничения",
    "operator": "Условие сравнения",
    "value": "Значение",
    "origin": "Источник ограничения",
    "schema_version": "Версия схемы",
    "version": "Версия",
    "policy_id": "Идентификатор политики",
    "status": "Статус политики",
    "scheduler": "Планирование вопросов",
    "stop": "Правила остановки",
    "resources": "Лимиты ресурсов",
    "runtime": "Среда выполнения",
    "evaluation": "Настройки эксперимента",
}

CONSTRAINT_TYPES = {
    "USER": "Задано пользователем",
    "REGULATORY": "Нормативное требование",
    "PHYSICAL": "Физическое ограничение",
    "TECHNICAL": "Техническое ограничение",
    "METHODOLOGICAL_EVALUATION": "Условие проверки методологии",
}
OPERATORS = {"eq": "равно", "lt": "меньше", "le": "не больше", "gt": "больше", "ge": "не меньше"}
POLICY_STATUSES = {
    "UNVALIDATED": "Экспериментальная, ещё не проверена",
    "PILOT_CALIBRATED": "Откалибрована на пилотных данных (по декларации автора)",
    "EVALUATED": "Оценена на данных эксперимента (по декларации автора)",
}


def byte_size(value: int | None) -> str:
    if value is None:
        return "Недоступно"
    for unit, divisor in (("GiB", 1024**3), ("MiB", 1024**2), ("KiB", 1024)):
        if value >= divisor:
            return f"{value / divisor:.2f}".rstrip("0").rstrip(".") + f" {unit}"
    return f"{value} байт"


def duration(value: int) -> str:
    hours, rest = divmod(value, 3600)
    minutes, seconds = divmod(rest, 60)
    return (
        " ".join(
            text
            for amount, text in (
                (hours, f"{hours} ч"),
                (minutes, f"{minutes} мин"),
                (seconds, f"{seconds} с"),
            )
            if amount
        )
        or "0 с"
    )


def repository_state(dirty: bool | None) -> str:
    return (
        "Недоступно" if dirty is None else "Есть незакоммиченные изменения" if dirty else "Чистый"
    )


def display_error(error: IAAIError) -> dict:
    """Translate known validation issues without changing application error contracts."""
    messages = []
    if isinstance(error.__cause__, ValidationError):
        for issue in error.__cause__.errors(include_input=False, include_url=False)[:10]:
            path = issue["loc"]
            label = (
                " → ".join(
                    f"строка {part + 1}"
                    if isinstance(part, int)
                    else FIELD_LABELS.get(part, "Поле расширенных настроек")
                    for part in path
                )
                or "Настройки исследования"
            )
            kind = issue["type"]
            if "source_cutoff" in path:
                hint = "Выберите дату в календаре или оставьте поле пустым. Формат: ГГГГ-ММ-ДД."
            elif kind == "missing":
                hint = "Заполните обязательное поле."
            elif kind in ("string_too_short", "string_pattern_mismatch"):
                hint = (
                    "Используйте латинские буквы, цифры, точку, дефис или подчёркивание."
                    if "name" in path
                    else "Введите непустой текст."
                )
            elif kind == "too_short":
                hint = "Добавьте хотя бы один элемент."
            elif kind == "extra_forbidden":
                hint = "Неизвестное поле. Проверьте схему в расширенных настройках."
            elif kind == "json_invalid":
                hint = "Некорректный JSON. Проверьте скобки, кавычки и запятые."
            elif kind in (
                "int_type",
                "float_type",
                "finite_number",
                "greater_than",
                "greater_than_equal",
                "less_than",
                "less_than_equal",
            ):
                hint = "Проверьте числовой тип, допустимый диапазон и положительные лимиты."
            elif kind == "literal_error":
                hint = "Выберите поддерживаемый тип, единицу или версию схемы."
            elif kind == "string_too_long":
                hint = "Текст слишком длинный. Сократите значение."
            else:
                hint = (
                    "Проверьте типы, единицы, уникальность показателей и совместимость полей. "
                    "Для набора вопросов укажите и ссылку, и версию либо оставьте оба пустыми."
                )
            messages.append(f"{label}: {hint}")
    elif error.code in {
        "VALIDATION_ERROR",
        "UNSAFE_URL",
        "IMPORT_PROVENANCE",
        "IMPORT_DATE",
        "TEXT_LIMIT",
        "EMPTY_TEXT",
        "EMPTY_CORPUS",
        "CORPUS_LIMIT",
        "OUTSIDE_SOURCE_CUTOFF",
        "ARTIFACT_NOT_ACCEPTABLE",
        "QUERY_LIMIT",
        "EMPTY_QUERY",
        "FTS5_UNAVAILABLE",
        "INDEX_VERSION_MISMATCH",
        "CHUNK_VERSION_MISMATCH",
        "RAW_CACHE_LIMIT",
        "CORPUS_CONFLICT",
    }:
        messages = [error.message]  # Form adapter messages are already Russian.
    elif error.code == "NOT_FOUND":
        messages = ["Исследование или сохранённая версия не найдены. Вернитесь к списку."]
    else:
        messages = ["Не удалось выполнить операцию. Проверьте базу данных на странице диагностики."]
    return {"messages": messages, "technical": error.as_dict()}
