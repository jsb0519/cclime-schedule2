"""Firebase RTDB /beautyzzang 네임스페이스 write (공개 write)."""
import requests


def build_payload(off_by_name: dict[str, list[str]], synced_at: str) -> dict:
    payload: dict = dict(off_by_name)
    payload["_syncedAt"] = synced_at
    return payload


def write_branch(base: str, year: int, month: int, branch: str, payload: dict, put=requests.put) -> int:
    if "/" in branch or ".." in branch:
        raise ValueError(f"invalid branch key: {branch!r}")
    url = f"{base}/beautyzzang/{year:04d}_{month:02d}/{branch}.json"
    return put(url, json=payload, timeout=20).status_code
