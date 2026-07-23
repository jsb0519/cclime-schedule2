from bz_sync.names import resolve_bans

SYS = ["대기", "지원", "당일취소"]

def test_maps_oid_and_filters_system():
    bans = {847079: {"off": ["2026-07-01"], "half": [], "reasons": {"2026-07-01": "휴무"}},
            564937: {"off": ["2026-07-02"], "half": [], "reasons": {"2026-07-02": "휴무"}},  # 시스템 → 제외
            860807: {"off": [], "half": ["2026-07-22"], "reasons": {"2026-07-22": "반차"}}}
    oid2name = {847079: "김효은", 564937: "대기", 860807: "박세영"}
    assert resolve_bans(bans, oid2name, SYS, {}) == {
        "김효은": {"off": ["2026-07-01"], "half": [], "reasons": {"2026-07-01": "휴무"}},
        "박세영": {"off": [], "half": ["2026-07-22"], "reasons": {"2026-07-22": "반차"}},
    }

def test_unknown_oid_becomes_placeholder():
    bans = {999999: {"off": ["2026-07-01"], "half": [], "reasons": {"2026-07-01": "휴무"}}}
    assert resolve_bans(bans, {}, SYS, {}) == {
        "oid:999999": {"off": ["2026-07-01"], "half": [], "reasons": {"2026-07-01": "휴무"}}}

def test_name_map_rename_exclude_and_merge_dup():
    bans = {1: {"off": ["2026-07-01"], "half": [], "reasons": {"2026-07-01": "휴무"}},
            2: {"off": [], "half": ["2026-07-03"], "reasons": {"2026-07-03": "반차"}},   # 2도 김효은 → 합집합
            3: {"off": ["2026-07-09"], "half": [], "reasons": {"2026-07-09": "휴무"}}}   # 제외대상
    oid2name = {1: "김효은(신사)", 2: "김효은(신사)", 3: "제외대상"}
    out = resolve_bans(bans, oid2name, SYS, {"김효은(신사)": "김효은", "제외대상": ""})
    assert out == {"김효은": {"off": ["2026-07-01"], "half": ["2026-07-03"],
                             "reasons": {"2026-07-01": "휴무", "2026-07-03": "반차"}}}
