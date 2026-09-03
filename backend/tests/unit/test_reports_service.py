import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from fastapi import HTTPException

from app.modules.reports.schemas import ReportPeriod
from app.modules.reports.service import _resolve_period


class TestResolvePeriod:
    def test_all_time_has_no_bounds(self) -> None:
        assert _resolve_period(ReportPeriod.ALL_TIME, None, None) == (None, None)

    def test_today_starts_at_midnight_utc(self) -> None:
        start, end = _resolve_period(ReportPeriod.TODAY, None, None)
        now = datetime.now(timezone.utc)
        assert start.date() == now.date()
        assert start.hour == 0 and start.minute == 0

    def test_seven_days_spans_roughly_a_week(self) -> None:
        start, end = _resolve_period(ReportPeriod.SEVEN_DAYS, None, None)
        assert (end - start) - timedelta(days=7) < timedelta(seconds=5)

    def test_thirty_days_spans_roughly_a_month(self) -> None:
        start, end = _resolve_period(ReportPeriod.THIRTY_DAYS, None, None)
        assert (end - start) - timedelta(days=30) < timedelta(seconds=5)

    def test_custom_uses_the_provided_bounds(self) -> None:
        date_from = datetime(2026, 1, 1, tzinfo=timezone.utc)
        date_to = datetime(2026, 1, 31, tzinfo=timezone.utc)
        assert _resolve_period(ReportPeriod.CUSTOM, date_from, date_to) == (date_from, date_to)

    def test_custom_without_dates_is_rejected(self) -> None:
        with pytest.raises(HTTPException) as exc:
            _resolve_period(ReportPeriod.CUSTOM, None, None)
        assert exc.value.status_code == 422

    def test_custom_with_date_from_after_date_to_is_rejected(self) -> None:
        date_from = datetime(2026, 2, 1, tzinfo=timezone.utc)
        date_to = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with pytest.raises(HTTPException) as exc:
            _resolve_period(ReportPeriod.CUSTOM, date_from, date_to)
        assert exc.value.status_code == 422
