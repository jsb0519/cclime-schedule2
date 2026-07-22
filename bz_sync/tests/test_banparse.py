import json
from pathlib import Path
from bz_sync.banparse import parse_bans, parse_staff_names

FIX = Path(__file__).parent / "fixtures"

def test_parse_bans_splits_full_and_half():
    ban = json.loads((FIX / "banlist_sinsa_2026_07.json").read_text(encoding="utf-8"))
    rec = parse_bans(ban)
    assert rec[847079] == {"off": ["2026-07-01", "2026-07-06"], "half": []}   # 종일휴무
    assert rec[857465] == {"off": ["2026-07-04", "2026-07-05"], "half": []}
    assert rec[860807] == {"off": [], "half": ["2026-07-22"]}                  # 부분금지 → half

def test_parse_bans_dedup_sorted():
    ban = [
        {"oidStaff": 1, "strDate": "2026-07-05", "n1DayHoliday": 1},
        {"oidStaff": 1, "strDate": "2026-07-02", "n1DayHoliday": 1},
        {"oidStaff": 1, "strDate": "2026-07-05", "n1DayHoliday": 1},
        {"oidStaff": 1, "strDate": "2026-07-10", "n1DayHoliday": 0},
        {"oidStaff": 1, "strDate": "2026-07-10", "n1DayHoliday": 0},
    ]
    assert parse_bans(ban) == {1: {"off": ["2026-07-02", "2026-07-05"], "half": ["2026-07-10"]}}

def test_parse_staff_names():
    rv = json.loads((FIX / "reservationlist_staffnames_sinsa.json").read_text(encoding="utf-8"))
    names = parse_staff_names(rv)
    assert names[847079] == "김효은"
    assert names[857465] == "박세영"
    assert names[564937] == "대기"
