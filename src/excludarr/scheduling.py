"""Five-field cron validation and explicit local-wall-time DST policy."""

import re
from datetime import UTC, datetime
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import CroniterBadCronError, CroniterBadDateError, croniter
from pydantic import BaseModel, ConfigDict, PlainValidator, field_validator

_NAMES = {
    "jan",
    "feb",
    "mar",
    "apr",
    "may",
    "jun",
    "jul",
    "aug",
    "sep",
    "oct",
    "nov",
    "dec",
    "mon",
    "tue",
    "wed",
    "thu",
    "fri",
    "sat",
    "sun",
}


def validate_schedule(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("schedule must be a five-field cron expression")  # noqa: TRY004 - pydantic validation
    value = " ".join(value.split())
    if (
        len(value.split()) != 5
        or not re.fullmatch(r"[0-9A-Za-z*,/ -]+", value)
        or any(name.lower() not in _NAMES for name in re.findall("[A-Za-z]+", value))
    ):
        raise ValueError("schedule must use standard five-field cron notation")
    try:
        croniter(value, datetime(2000, 1, 1), day_or=True, max_years_between_matches=400).get_next(
            datetime
        )
    except (CroniterBadCronError, CroniterBadDateError, ValueError, KeyError) as error:
        raise ValueError("invalid or impossible cron schedule") from error
    return value


Schedule = Annotated[str | None, PlainValidator(validate_schedule)]


class SchedulerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timezone: str = "UTC"

    @field_validator("timezone")
    @classmethod
    def _timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("timezone must name an available IANA zone") from error
        return value


def next_occurrence(expression: str, after: datetime, timezone: str) -> datetime:
    if after.tzinfo is None:
        raise ValueError("schedule timestamps must be timezone-aware")
    expression = validate_schedule(expression)
    zone = ZoneInfo(timezone)
    after = after.astimezone(UTC)
    wall = after.astimezone(zone).replace(tzinfo=None)
    iterator = croniter(expression, wall, day_or=True, max_years_between_matches=400)
    while True:
        candidate = iterator.get_next(datetime)
        instant = candidate.replace(tzinfo=zone, fold=0).astimezone(UTC)
        # Round-trip rejects nonexistent minutes; fold=0 prevents autumn replay.
        if instant > after and instant.astimezone(zone).replace(tzinfo=None) == candidate:
            return instant


def schedule_warnings(config, now: datetime) -> list[str]:
    from datetime import timedelta

    warnings = []
    if config.list_proxy:
        for name, rule in config.list_proxy.lists.items():
            if rule.schedule is not None:
                first = next_occurrence(rule.schedule, now, config.scheduler.timezone)
                second = next_occurrence(rule.schedule, first, config.scheduler.timezone)
                if second - first >= timedelta(hours=6):
                    warnings.append(
                        f"list {name!r}: next refresh gap is at least six hours; snapshots may expire"
                    )
    return warnings
