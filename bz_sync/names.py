"""oidStaff → 근무표 이름 해석: 이름 치환 + 시스템계정/제외 필터."""


def resolve_bans(bans_by_oid: dict[int, dict[str, list[str]]], oid_to_name: dict[int, str],
                 system_accounts: list[str], name_map: dict[str, str]) -> dict[str, dict[str, list[str]]]:
    """oidStaff→근무표 이름 해석 + 시스템계정/제외 필터. off·half 중첩 구조 보존, 동명이인 합집합."""
    sys_set = set(system_accounts)
    acc: dict[str, dict[str, set[str]]] = {}
    for oid, rec in bans_by_oid.items():
        name = oid_to_name.get(oid) or f"oid:{oid}"
        if name in sys_set:
            continue
        mapped = name_map.get(name, name)
        if mapped == "":
            continue
        slot = acc.setdefault(mapped, {"off": set(), "half": set()})
        slot["off"].update(rec.get("off", []))
        slot["half"].update(rec.get("half", []))
    return {name: {"off": sorted(v["off"]), "half": sorted(v["half"])} for name, v in acc.items()}
