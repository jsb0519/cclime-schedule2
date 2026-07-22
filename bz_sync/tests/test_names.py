from bz_sync.names import resolve_bans

SYS = ["대기", "지원", "당일취소"]

def test_maps_oid_and_filters_system():
    bans = {847079: {"off": ["2026-07-01"], "half": []},
            564937: {"off": ["2026-07-02"], "half": []},      # 시스템계정 → 제외
            860807: {"off": [], "half": ["2026-07-22"]}}
    oid2name = {847079: "김효은", 564937: "대기", 860807: "박세영"}
    assert resolve_bans(bans, oid2name, SYS, {}) == {
        "김효은": {"off": ["2026-07-01"], "half": []},
        "박세영": {"off": [], "half": ["2026-07-22"]},
    }

def test_unknown_oid_becomes_placeholder():
    bans = {999999: {"off": ["2026-07-01"], "half": []}}
    assert resolve_bans(bans, {}, SYS, {}) == {"oid:999999": {"off": ["2026-07-01"], "half": []}}

def test_name_map_rename_exclude_and_merge_dup():
    bans = {1: {"off": ["2026-07-01"], "half": []},
            2: {"off": [], "half": ["2026-07-03"]},           # 2도 김효은으로 매핑 → 합집합
            3: {"off": ["2026-07-09"], "half": []}}            # 제외대상
    oid2name = {1: "김효은(신사)", 2: "김효은(신사)", 3: "제외대상"}
    out = resolve_bans(bans, oid2name, SYS, {"김효은(신사)": "김효은", "제외대상": ""})
    assert out == {"김효은": {"off": ["2026-07-01"], "half": ["2026-07-03"]}}
