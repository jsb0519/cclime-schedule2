"""Firebase RTDB /beautyzzang 네임스페이스 write (공개 write)."""
import re

import requests

# Firebase RTDB 키 금지문자(. # $ [ ] /)를 '_'로 치환.
# 프론트엔드 index.html의 fbBranchKey와 동일 규칙이어야 read/write가 맞물린다.
_FB_KEY_BAD = re.compile(r"[.#$\[\]/]")


def build_payload(bans_by_name: dict[str, dict], synced_at: str) -> dict:
    """{name: {"off":[...], "half":[...]}} + _syncedAt 를 Firebase 노드 페이로드로."""
    payload: dict = dict(bans_by_name)
    payload["_syncedAt"] = synced_at
    return payload


def fb_key(branch: str) -> str:
    """지점키를 Firebase RTDB 경로 토큰으로 변환.
    RTDB 키는 . # $ [ ] / 를 금지한다. 지점키('01. 신사본점')는 번호 뒤에 '.'을
    포함하므로 그대로 쓰면 400(Invalid token in path) → 금지문자를 '_'로 치환.
    프론트엔드 index.html의 fbBranchKey와 동일 규칙('01. 신사본점' → '01_ 신사본점').
    치환으로 '/'·'..'도 무해화되어 네임스페이스 이스케이프가 불가능하다."""
    return _FB_KEY_BAD.sub("_", branch)


def write_branch(base: str, year: int, month: int, branch: str, payload: dict, put=requests.put) -> int:
    url = f"{base}/beautyzzang/{year:04d}_{month:02d}/{fb_key(branch)}.json"
    return put(url, json=payload, timeout=20).status_code
