"""oidStaff → 근무표 이름 해석: 이름 치환 + 시스템계정/제외 필터."""


def resolve(off_by_oid: dict[int, list[str]], oid_to_name: dict[int, str],
            system_accounts: list[str], name_map: dict[str, str]) -> dict[str, list[str]]:
    sys_set = set(system_accounts)
    out: dict[str, list[str]] = {}
    for oid, dates in off_by_oid.items():
        name = oid_to_name.get(oid) or f"oid:{oid}"
        if name in sys_set:
            continue
        mapped = name_map.get(name, name)
        if mapped == "":
            continue
        out[mapped] = dates
    return out
