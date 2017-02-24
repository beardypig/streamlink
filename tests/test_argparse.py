import pytest
from streamlink_cli.argparser import hours_minutes_seconds


@pytest.mark.parametrize("hms,expected", [
    ("2m", 120),
    ("1m", 60),
    ("100m", 6000),
    ("1m10s", 70),
    ("1h", 3600),
    ("1h2s", 3602),
    ("1h1m", 3660),
    ("1s", 1),
    ("", 0)
])
def test_hour_mins_seconds(hms, expected):
    assert expected == hours_minutes_seconds(hms)
