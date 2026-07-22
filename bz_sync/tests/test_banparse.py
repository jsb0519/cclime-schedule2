import json
from pathlib import Path
from bz_sync.banparse import parse_offdays, parse_staff_names

FIX = Path(__file__).parent / "fixtures"

def test_parse_offdays_fullday_only():
    ban = json.loads((FIX / "banlist_sinsa_2026_07.json").read_text(encoding="utf-8"))
    off = parse_offdays(ban)
    assert off[847079] == ["2026-07-01", "2026-07-06"]      # 종일 휴무 2건
    assert off[857465] == ["2026-07-04", "2026-07-05"]
    assert 860807 not in off                                 # n1DayHoliday=0(부분) → 제외

def test_parse_offdays_dedup_sorted():
    ban = [
        {"oidStaff": 1, "strDate": "2026-07-05", "n1DayHoliday": 1},
        {"oidStaff": 1, "strDate": "2026-07-02", "n1DayHoliday": 1},
        {"oidStaff": 1, "strDate": "2026-07-05", "n1DayHoliday": 1},
    ]
    assert parse_offdays(ban) == {1: ["2026-07-02", "2026-07-05"]}

def test_parse_staff_names():
    rv = json.loads((FIX / "reservationlist_staffnames_sinsa.json").read_text(encoding="utf-8"))
    names = parse_staff_names(rv)
    assert names[847079] == "김효은"
    assert names[857465] == "박세영"
    assert names[564937] == "대기"
