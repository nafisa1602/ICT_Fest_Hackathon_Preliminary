from datetime import datetime, timezone, timedelta
from app.timeutils import parse_input_datetime, iso_utc

def test_parse_input_datetime_naive():
    # Naive inputs should be treated as UTC as-is
    val = "2026-07-09T18:00:00"
    dt = parse_input_datetime(val)
    assert dt == datetime(2026, 7, 9, 18, 0, 0)
    assert dt.tzinfo is None

def test_parse_input_datetime_utc_offset():
    # +02:00 offset should convert 18:00:00 to 16:00:00 UTC
    val = "2026-07-09T18:00:00+02:00"
    dt = parse_input_datetime(val)
    assert dt == datetime(2026, 7, 9, 16, 0, 0)
    assert dt.tzinfo is None

def test_parse_input_datetime_negative_offset():
    # -05:00 offset should convert 18:00:00 to 23:00:00 UTC
    val = "2026-07-09T18:00:00-05:00"
    dt = parse_input_datetime(val)
    assert dt == datetime(2026, 7, 9, 23, 0, 0)
    assert dt.tzinfo is None

def test_parse_input_datetime_z_suffix():
    # Z (UTC) suffix should parse to naive UTC
    val = "2026-07-09T18:00:00Z"
    dt = parse_input_datetime(val)
    assert dt == datetime(2026, 7, 9, 18, 0, 0)
    assert dt.tzinfo is None

def test_iso_utc():
    dt = datetime(2026, 7, 9, 18, 0, 0)
    assert iso_utc(dt) == "2026-07-09T18:00:00+00:00"
