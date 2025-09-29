"""Pydantic models for schedule configuration with automatic JSON schema generation."""

from enum import Enum
from typing import Optional
from typing import Union

from pydantic import BaseModel
from pydantic import Field
from pydantic import ValidationError


class ScheduleType(str, Enum):
    """Schedule type enumeration."""

    ONCE = "once"
    CRON = "cron"
    INTERVAL = "interval"


class OnceSchedule(BaseModel):
    """One-time schedule configuration."""

    when: str = Field(
        ...,
        description="ISO datetime string for when to run (e.g., '2024-01-16T14:00:00')",
    )


class CronSchedule(BaseModel):
    """Cron-based schedule configuration using APScheduler CronTrigger format."""

    year: Optional[int] = Field(None, ge=1970, le=2099, description="Year (1970-2099)")
    month: Optional[int] = Field(None, ge=1, le=12, description="Month (1-12)")
    day: Optional[int] = Field(None, ge=1, le=31, description="Day of month (1-31)")
    week: Optional[int] = Field(None, ge=1, le=53, description="Week of year (1-53)")
    day_of_week: Optional[Union[int, str]] = Field(
        None, description="Day of week (0-6 for Mon-Sun, or 'mon', 'tue', etc.)"
    )
    hour: Optional[int] = Field(None, ge=0, le=23, description="Hour (0-23)")
    minute: Optional[int] = Field(None, ge=0, le=59, description="Minute (0-59)")
    second: Optional[int] = Field(None, ge=0, le=59, description="Second (0-59)")
    start_date: Optional[str] = Field(
        None, description="Start date as ISO datetime string"
    )
    end_date: Optional[str] = Field(None, description="End date as ISO datetime string")

    def __init__(self, **data):
        super().__init__(**data)
        # Validate that at least one time unit is specified
        time_fields = [
            "year",
            "month",
            "day",
            "week",
            "day_of_week",
            "hour",
            "minute",
            "second",
        ]
        if not any(getattr(self, field) for field in time_fields):
            raise ValueError(
                "At least one time unit (year, month, day, week, day_of_week, hour,"
                " minute, second) must be specified"
            )


class IntervalSchedule(BaseModel):
    """Interval-based schedule configuration."""

    weeks: Optional[int] = Field(None, ge=0, description="Number of weeks between runs")
    days: Optional[int] = Field(None, ge=0, description="Number of days between runs")
    hours: Optional[int] = Field(None, ge=0, description="Number of hours between runs")
    minutes: Optional[int] = Field(
        None, ge=0, description="Number of minutes between runs"
    )
    seconds: Optional[int] = Field(
        None, ge=0, description="Number of seconds between runs"
    )
    start_date: Optional[str] = Field(
        None, description="ISO datetime to start from (defaults to now)"
    )
    end_date: Optional[str] = Field(None, description="ISO datetime to end at")

    def __init__(self, **data):
        super().__init__(**data)
        # Validate that at least one interval unit is specified
        interval_fields = ["weeks", "days", "hours", "minutes", "seconds"]
        if not any(getattr(self, field) for field in interval_fields):
            raise ValueError(
                "At least one interval unit (weeks, days, hours, minutes, seconds) must"
                " be specified"
            )


# Union type with discriminator for automatic validation
ScheduleConfig = Union[OnceSchedule, CronSchedule, IntervalSchedule]


def schedule_config_to_dict(config: ScheduleConfig) -> dict:
    """Convert ScheduleConfig to dictionary for database storage."""
    return config.model_dump(exclude_none=True)


def dict_to_schedule_config(data: dict, schedule_type: str) -> ScheduleConfig:
    """Convert dictionary to ScheduleConfig for validation.

    Args:
        data: Dictionary containing schedule configuration
        schedule_type: The schedule type ("once", "cron", or "interval")

    Returns:
        Validated ScheduleConfig instance
    """
    try:
        if schedule_type == "once":
            return OnceSchedule.model_validate(data)
        elif schedule_type == "cron":
            return CronSchedule.model_validate(data)
        elif schedule_type == "interval":
            return IntervalSchedule.model_validate(data)
        else:
            raise ValueError(f"Unknown schedule type: {schedule_type}")
    except ValidationError as e:
        raise ValueError(f"Invalid schedule configuration: {e}") from e
