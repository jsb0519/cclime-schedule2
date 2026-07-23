import json
from pathlib import Path
from bz_sync.banparse import parse_bans, parse_staff_names

FIX = Path(__file__).parent / "fixtures"

def test_parse_bans_fixture_off_half_reasons():
    # 픽스처 860807 부분금지 사유='기타' → 허용목록에 '기타'가 있어야 half로 잡힌다.
    ban = json.loads((FIX / "banlist_sinsa_2026_07.json").read_text(encoding="utf-8"))
    rec = parse_bans(ban, ["기타"])
    assert rec[847079]["off"] == ["2026-07-01", "2026-07-06"]           # 종일휴무
    assert rec[847079]["half"] == []
    assert set(rec[847079]["reasons"]) == {"2026-07-01", "2026-07-06"}  # 종일 사유 기록됨
    assert rec[860807]["half"] == ["2026-07-22"]                         # '기타' 부분금지 → half
    assert rec[860807]["reasons"]["2026-07-22"] == "기타"

def test_parse_bans_fulldays_read_regardless_of_reason():
    # 종일휴무(=1)는 사유 무관 전부 읽는다(허용목록과 상관없이).
    ban = [
        {"oidStaff": 1, "strDate": "2026-07-01", "n1DayHoliday": 1, "strBanReason": "담당자 휴무"},
        {"oidStaff": 1, "strDate": "2026-07-02", "n1DayHoliday": 1, "strBanReason": "기타"},
        {"oidStaff": 1, "strDate": "2026-07-03", "n1DayHoliday": 1, "strBanReason": ""},
    ]
    rec = parse_bans(ban, ["휴무", "휴가", "연차", "반차"])   # 허용목록에 위 사유 없어도 종일은 전부
    assert rec[1]["off"] == ["2026-07-01", "2026-07-02", "2026-07-03"]
    assert rec[1]["half"] == []
    assert rec[1]["reasons"] == {"2026-07-01": "담당자 휴무", "2026-07-02": "기타", "2026-07-03": ""}

def test_parse_bans_partial_reason_filter():
    ban = [
        {"oidStaff": 1, "strDate": "2026-07-10", "n1DayHoliday": 0, "strBanReason": "반차"},   # 허용
        {"oidStaff": 1, "strDate": "2026-07-11", "n1DayHoliday": 0, "strBanReason": "기타"},   # 상시블록 → 제외
        {"oidStaff": 1, "strDate": "2026-07-12", "n1DayHoliday": 0, "strBanReason": "식사"},   # 제외
        {"oidStaff": 2, "strDate": "2026-07-13", "n1DayHoliday": 0, "strBanReason": " 휴가 "}, # 트림 후 허용
    ]
    rec = parse_bans(ban, ["휴무", "휴가", "연차", "반차"])
    assert rec[1] == {"off": [], "half": ["2026-07-10"], "reasons": {"2026-07-10": "반차"}}
    assert rec[2] == {"off": [], "half": ["2026-07-13"], "reasons": {"2026-07-13": "휴가"}}

def test_parse_bans_dedup_and_fullday_reason_priority():
    ban = [
        {"oidStaff": 1, "strDate": "2026-07-05", "n1DayHoliday": 1, "strBanReason": "휴무"},
        {"oidStaff": 1, "strDate": "2026-07-02", "n1DayHoliday": 1, "strBanReason": "연차"},
        {"oidStaff": 1, "strDate": "2026-07-05", "n1DayHoliday": 1, "strBanReason": "휴무"},   # 중복 dedupe
        {"oidStaff": 1, "strDate": "2026-07-05", "n1DayHoliday": 0, "strBanReason": "반차"},   # 같은날 부분
    ]
    rec = parse_bans(ban, ["반차"])
    assert rec[1]["off"] == ["2026-07-02", "2026-07-05"]
    assert rec[1]["half"] == ["2026-07-05"]
    assert rec[1]["reasons"]["2026-07-05"] == "휴무"      # 종일 사유가 우선(부분이 덮지 않음)
    assert rec[1]["reasons"]["2026-07-02"] == "연차"

def test_parse_staff_names():
    rv = json.loads((FIX / "reservationlist_staffnames_sinsa.json").read_text(encoding="utf-8"))
    names = parse_staff_names(rv)
    assert names[847079] == "김효은"
    assert names[857465] == "박세영"
    assert names[564937] == "대기"
