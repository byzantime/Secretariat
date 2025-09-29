"""Unit tests for schedule configuration models."""

import pytest

from src.models.schedule_config import CronSchedule
from src.models.schedule_config import IntervalSchedule
from src.models.schedule_config import OnceSchedule
from src.models.schedule_config import dict_to_schedule_config
from src.models.schedule_config import schedule_config_to_dict


class TestScheduleConfigModels:
    """Test schedule configuration Pydantic models."""

    def test_once_schedule_creation(self):
        """Test OnceSchedule model creation and validation."""
        schedule = OnceSchedule(when="2024-01-16T14:00:00")
        assert schedule.when == "2024-01-16T14:00:00"

    def test_cron_schedule_creation(self):
        """Test CronSchedule model creation and validation."""
        schedule = CronSchedule(hour=14, minute=30)
        assert schedule.hour == 14
        assert schedule.minute == 30
        assert schedule.second is None

    def test_cron_schedule_requires_at_least_one_field(self):
        """Test that CronSchedule requires at least one time field."""
        with pytest.raises(ValueError, match="At least one time unit"):
            CronSchedule()

    def test_interval_schedule_creation(self):
        """Test IntervalSchedule model creation and validation."""
        schedule = IntervalSchedule(minutes=2)
        assert schedule.minutes == 2
        assert schedule.hours is None

    def test_interval_schedule_multiple_units(self):
        """Test IntervalSchedule with multiple time units."""
        schedule = IntervalSchedule(hours=1, minutes=30)
        assert schedule.hours == 1
        assert schedule.minutes == 30
        assert schedule.seconds is None

    def test_interval_schedule_requires_at_least_one_field(self):
        """Test that IntervalSchedule requires at least one interval field."""
        with pytest.raises(ValueError, match="At least one interval unit"):
            IntervalSchedule()


class TestScheduleConfigSerialization:
    """Test schedule configuration serialization with None value exclusion."""

    def test_schedule_config_to_dict_excludes_none_interval(self):
        """Test that schedule_config_to_dict excludes None values for IntervalSchedule."""
        schedule = IntervalSchedule(minutes=2)
        result = schedule_config_to_dict(schedule)

        # Should only contain minutes, no None values, no type field
        expected = {"minutes": 2}
        assert result == expected

        # Verify None values are excluded
        assert "weeks" not in result
        assert "days" not in result
        assert "hours" not in result
        assert "seconds" not in result
        assert "start_date" not in result
        assert "end_date" not in result

    def test_schedule_config_to_dict_excludes_none_cron(self):
        """Test that schedule_config_to_dict excludes None values for CronSchedule."""
        schedule = CronSchedule(hour=14, minute=30)
        result = schedule_config_to_dict(schedule)

        expected = {"hour": 14, "minute": 30}
        assert result == expected

        # Verify None values are excluded
        assert "year" not in result
        assert "month" not in result
        assert "day" not in result
        assert "second" not in result

    def test_schedule_config_to_dict_excludes_none_once(self):
        """Test that schedule_config_to_dict excludes None values for OnceSchedule."""
        schedule = OnceSchedule(when="2024-01-16T14:00:00")
        result = schedule_config_to_dict(schedule)

        expected = {"when": "2024-01-16T14:00:00"}
        assert result == expected

    def test_schedule_config_to_dict_multiple_interval_values(self):
        """Test schedule_config_to_dict with multiple interval values."""
        schedule = IntervalSchedule(hours=1, minutes=30, seconds=45)
        result = schedule_config_to_dict(schedule)

        expected = {"hours": 1, "minutes": 30, "seconds": 45}
        assert result == expected

        # Verify unset values are excluded
        assert "weeks" not in result
        assert "days" not in result


class TestScheduleConfigRoundTrip:
    """Test round-trip conversion between models and dictionaries."""

    def test_interval_schedule_roundtrip(self):
        """Test IntervalSchedule round-trip conversion."""
        original = IntervalSchedule(minutes=2)

        # Convert to dict (excludes None values)
        config_dict = schedule_config_to_dict(original)

        # Convert back to model (needs schedule_type)
        restored = dict_to_schedule_config(config_dict, "interval")

        # Models should be equivalent
        assert original == restored
        assert isinstance(restored, IntervalSchedule)
        assert restored.minutes == 2

    def test_cron_schedule_roundtrip(self):
        """Test CronSchedule round-trip conversion."""
        original = CronSchedule(hour=14, minute=30)

        config_dict = schedule_config_to_dict(original)
        restored = dict_to_schedule_config(config_dict, "cron")

        assert original == restored
        assert isinstance(restored, CronSchedule)
        assert restored.hour == 14
        assert restored.minute == 30

    def test_once_schedule_roundtrip(self):
        """Test OnceSchedule round-trip conversion."""
        original = OnceSchedule(when="2024-01-16T14:00:00")

        config_dict = schedule_config_to_dict(original)
        restored = dict_to_schedule_config(config_dict, "once")

        assert original == restored
        assert isinstance(restored, OnceSchedule)
        assert restored.when == "2024-01-16T14:00:00"


class TestScheduleConfigIntegration:
    """Test schedule configuration integration with APScheduler."""

    def test_interval_config_compatible_with_apscheduler(self):
        """Test that clean interval config works with APScheduler triggers."""
        from apscheduler.triggers.interval import IntervalTrigger

        schedule = IntervalSchedule(minutes=2)
        config_dict = schedule_config_to_dict(schedule)

        # Clean unpacking - no filtering needed!
        trigger = IntervalTrigger(**config_dict)
        assert trigger.interval.total_seconds() == 120  # 2 minutes

    def test_cron_config_compatible_with_apscheduler(self):
        """Test that clean cron config works with APScheduler triggers."""
        from apscheduler.triggers.cron import CronTrigger

        schedule = CronSchedule(hour=14, minute=30)
        config_dict = schedule_config_to_dict(schedule)

        # Clean unpacking - no filtering needed!
        trigger = CronTrigger(**config_dict)

        # Verify trigger was created successfully (CronTrigger doesn't expose fields directly)
        assert trigger is not None
        assert str(trigger)  # Should have a string representation

    def test_once_config_compatible_with_apscheduler(self):
        """Test that once config works with APScheduler triggers."""
        from datetime import datetime

        from apscheduler.triggers.date import DateTrigger

        when_str = "2024-01-16T14:00:00"
        schedule = OnceSchedule(when=when_str)
        config_dict = schedule_config_to_dict(schedule)

        # DateTrigger expects a datetime object
        run_date = datetime.fromisoformat(config_dict["when"])
        trigger = DateTrigger(run_date=run_date)

        # DateTrigger may add timezone info, so compare the core datetime components
        assert trigger.run_date.replace(tzinfo=None) == run_date
        assert trigger is not None


class TestScheduleConfigValidation:
    """Test schedule configuration validation edge cases."""

    def test_dict_to_schedule_config_invalid_type(self):
        """Test dict_to_schedule_config with invalid schedule type."""
        with pytest.raises(ValueError, match="Unknown schedule type"):
            dict_to_schedule_config({"minutes": 2}, "invalid")

    def test_dict_to_schedule_config_validation_error(self):
        """Test dict_to_schedule_config with invalid data."""
        with pytest.raises(ValueError, match="Invalid schedule configuration"):
            dict_to_schedule_config({}, "interval")  # Missing required interval field
