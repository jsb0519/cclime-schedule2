"""뷰티짱 StatusBoardV2 JSON → 집계. 네트워크 의존 없음."""


def parse_bans(ban: list[dict], half_reasons: list[str]) -> dict[int, dict[str, list[str]]]:
    """BanList JSON → {oidStaff: {"off":[YYYY-MM-DD], "half":[YYYY-MM-DD]}}.
    n1DayHoliday==1 → 종일휴무(off).
    ==0 → 시간대 부분금지지만, 대부분은 '기타' 사유로 매 근무일 붙는 상시 예약차단 블록(반차 아님).
      → strBanReason이 half_reasons(예: 반차·연차·병가·휴무)에 있는 부분금지만 half로 집계.
    같은 날 중복은 dedupe."""
    reasons = set(half_reasons)
    off: dict[int, set[str]] = {}
    half: dict[int, set[str]] = {}
    for row in ban:
        oid = row.get("oidStaff")
        date = row.get("strDate")
        if oid is None or not date:
            continue
        flag = row.get("n1DayHoliday")
        if flag == 1:
            off.setdefault(int(oid), set()).add(date[:10])
        elif flag == 0 and (row.get("strBanReason") or "").strip() in reasons:
            half.setdefault(int(oid), set()).add(date[:10])
    oids = set(off) | set(half)
    return {oid: {"off": sorted(off.get(oid, set())),
                  "half": sorted(half.get(oid, set()))} for oid in oids}


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
