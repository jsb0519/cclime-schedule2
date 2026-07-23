"""뷰티짱 StatusBoardV2 JSON → 집계. 네트워크 의존 없음."""


def parse_bans(ban: list[dict], half_reasons: list[str]) -> dict[int, dict]:
    """BanList JSON → {oidStaff: {"off":[YYYY-MM-DD], "half":[YYYY-MM-DD], "reasons":{date: 사유}}}.
    n1DayHoliday==1 → 종일휴무(off): 사유 무관 전부 집계(하루 통째 차단 = 쉬는 날).
    ==0 → 시간대 부분금지: 대부분 '기타' 사유로 매 근무일 붙는 상시 예약차단 블록(반차 아님)이므로,
      strBanReason이 half_reasons(휴무·휴가·연차·반차)에 있는 것만 half로 집계.
    reasons: 화면 표시용 날짜별 사유(종일이 우선, 중복 dedupe)."""
    reasons_set = set(half_reasons)
    off: dict[int, set[str]] = {}
    half: dict[int, set[str]] = {}
    reason_by: dict[int, dict[str, str]] = {}
    for row in ban:
        oid = row.get("oidStaff")
        date = row.get("strDate")
        if oid is None or not date:
            continue
        oid = int(oid)
        d = date[:10]
        rsn = (row.get("strBanReason") or "").strip()
        flag = row.get("n1DayHoliday")
        if flag == 1:
            off.setdefault(oid, set()).add(d)
            reason_by.setdefault(oid, {})[d] = rsn                 # 종일 사유는 항상 기록(우선)
        elif flag == 0 and rsn in reasons_set:
            half.setdefault(oid, set()).add(d)
            reason_by.setdefault(oid, {}).setdefault(d, rsn)       # 종일이 이미 있으면 덮지 않음
    oids = set(off) | set(half)
    return {oid: {"off": sorted(off.get(oid, set())),
                  "half": sorted(half.get(oid, set())),
                  "reasons": reason_by.get(oid, {})} for oid in oids}


def parse_staff_names(rv: list[dict]) -> dict[int, str]:
    """ReservationList JSON → {oidStaff: strStaffName}."""
    names: dict[int, str] = {}
    for row in rv:
        oid = row.get("oidStaff")
        name = (row.get("strStaffName") or "").strip()
        if oid is None or not name:
            continue
        names[int(oid)] = name
    return names
