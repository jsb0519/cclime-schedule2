from bz_sync.names import resolve

SYS = ["대기", "지원", "당일취소"]

def test_maps_oid_to_name_and_filters_system():
    off = {847079: ["2026-07-01"], 564937: ["2026-07-02"], 860807: ["2026-07-03"]}
    oid2name = {847079: "김효은", 564937: "대기", 860807: "지원"}
    assert resolve(off, oid2name, SYS, {}) == {"김효은": ["2026-07-01"]}

def test_unknown_oid_becomes_placeholder():
    off = {999999: ["2026-07-01"]}
    assert resolve(off, {}, SYS, {}) == {"oid:999999": ["2026-07-01"]}

def test_name_map_rename_and_exclude():
    off = {1: ["2026-07-01"], 2: ["2026-07-02"]}
    oid2name = {1: "김효은(신사)", 2: "제외대상"}
    out = resolve(off, oid2name, SYS, {"김효은(신사)": "김효은", "제외대상": ""})
    assert out == {"김효은": ["2026-07-01"]}
