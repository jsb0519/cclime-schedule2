"""뷰티짱 StatusBoardV2 JSON → 집계. 네트워크 의존 없음."""


def parse_offdays(ban: list[dict]) -> dict[int, list[str]]:
    """BanList JSON → {oidStaff: [YYYY-MM-DD]}. 종일 휴무(n1DayHoliday==1)만."""
    acc: dict[int, set[str]] = {}
    for row in ban:
        if row.get("n1DayHoliday") != 1:
            continue
        oid = row.get("oidStaff")
        date = row.get("strDate")
        if oid is None or not date:
            continue
        acc.setdefault(int(oid), set()).add(date[:10])
    return {oid: sorted(dates) for oid, dates in acc.items()}


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
