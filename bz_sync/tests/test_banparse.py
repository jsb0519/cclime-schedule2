import json
from pathlib import Path
from bz_sync.banparse import parse_bans, parse_staff_names

FIX = Path(__file__).parent / "fixtures"

def test_parse_bans_splits_full_and_half():
    # 픽스처 860807 부분금지의 사유는 '기타' → 사유 허용목록에 '기타'가 있어야 half로 잡힌다.
    ban = json.loads((FIX / "banlist_sinsa_2026_07.json").read_text(encoding="utf-8"))
    rec = parse_bans(ban, ["기타"])
    assert rec[847079] == {"off": ["2026-07-01", "2026-07-06"], "half": []}   # 종일휴무
    assert rec[857465] == {"off": ["2026-07-04", "2026-07-05"], "half": []}
    assert rec[860807] == {"off": [], "half": ["2026-07-22"]}                  # '기타' 부분금지 → half

def test_parse_bans_reason_filter_excludes_unlisted():
    # 허용목록에 '기타'가 없으면 860807('기타' 부분금지)은 half에서 제외되어 oid 자체가 사라진다.
    ban = json.loads((FIX / "banlist_sinsa_2026_07.json").read_text(encoding="utf-8"))
    rec = parse_bans(ban, ["반차", "연차", "병가", "휴무"])
    assert 860807 not in rec                                                   # 상시블록(기타) 제외
    assert rec[847079] == {"off": ["2026-07-01", "2026-07-06"], "half": []}   # 종일휴무는 사유 무관

def test_parse_bans_reason_filter_keeps_listed_only():
    ban = [
        {"oidStaff": 1, "strDate": "2026-07-10", "n1DayHoliday": 0, "strBanReason": "반차"},   # 허용 → half
        {"oidStaff": 1, "strDate": "2026-07-11", "n1DayHoliday": 0, "strBanReason": "기타"},   # 상시블록 → 제외
        {"oidStaff": 1, "strDate": "2026-07-12", "n1DayHoliday": 0, "strBanReason": "식사"},   # 식사 → 제외
        {"oidStaff": 2, "strDate": "2026-07-13", "n1DayHoliday": 0, "strBanReason": " 연차 "}, # 공백 트림 후 허용
    ]
    rec = parse_bans(ban, ["반차", "연차", "병가", "휴무"])
    assert rec[1] == {"off": [], "half": ["2026-07-10"]}
    assert rec[2] == {"off": [], "half": ["2026-07-13"]}

def test_parse_bans_dedup_sorted():
    ban = [
        {"oidStaff": 1, "strDate": "2026-07-05", "n1DayHoliday": 1},
        {"oidStaff": 1, "strDate": "2026-07-02", "n1DayHoliday": 1},
        {"oidStaff": 1, "strDate": "2026-07-05", "n1DayHoliday": 1},
        {"oidStaff": 1, "strDate": "2026-07-10", "n1DayHoliday": 0, "strBanReason": "연차"},
        {"oidStaff": 1, "strDate": "2026-07-10", "n1DayHoliday": 0, "strBanReason": "연차"},
    ]
    assert parse_bans(ban, ["연차"]) == {1: {"off": ["2026-07-02", "2026-07-05"], "half": ["2026-07-10"]}}

def test_parse_staff_names():
    rv = json.loads((FIX / "reservationlist_staffnames_sinsa.json").read_text(encoding="utf-8"))
    names = parse_staff_names(rv)
    assert names[847079] == "김효은"
    assert names[857465] == "박세영"
    assert names[564937] == "대기"
