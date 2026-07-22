"""오케스트레이터: 지점 순회 → JSON 수집 → 집계 → Firebase write. 부분성공·실패알림."""
import json
import sys

from bz_sync.scrape import login, fetch_branch
from bz_sync.banparse import parse_offdays, parse_staff_names
from bz_sync.names import resolve
from bz_sync.fb import build_payload, write_branch


def summarize(results: dict[str, str]) -> str:
    fails = {b: r for b, r in results.items() if r != "ok"}
    if not fails:
        return f"뷰티짱 동기화 전체 성공 ({len(results)}지점)"
    lines = "\n".join(f"{b}: {r}" for b, r in fails.items())
    return f"뷰티짱 동기화 {len(fails)}/{len(results)} 실패\n{lines}"


def _months(now_iso: str) -> list[tuple[int, int]]:
    y, m = int(now_iso[:4]), int(now_iso[5:7])
    return [(y, m), (y + 1, 1) if m == 12 else (y, m + 1)]


def run(config: dict, creds: dict, now_iso: str) -> dict:
    from playwright.sync_api import sync_playwright

    base = config["firebase_base"]
    stores = json.load(open(config["branch_stores_path"], encoding="utf-8"))
    results: dict[str, str] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        login(page, creds)
        for branch, oid in stores.items():
            if branch.startswith("_"):
                continue
            try:
                for (y, m) in _months(now_iso):
                    ban, rv = fetch_branch(page, oid, y, m)
                    off = resolve(parse_offdays(ban), parse_staff_names(rv),
                                  config["system_accounts"], config["name_map"])
                    status = write_branch(base, y, m, branch, build_payload(off, now_iso))
                    if status >= 400:
                        raise RuntimeError(f"firebase {status}")
                results[branch] = "ok"
            except Exception as e:
                results[branch] = f"fail:{type(e).__name__}"
        browser.close()
    return results


def alert(config: dict, message: str) -> None:
    a = config.get("alert", {"type": "none"})
    if a.get("type") == "slack":
        import requests
        requests.post(a["webhook_url"], json={"text": message}, timeout=15)
    # 'none'/'nova'는 stdout 로깅으로 갈음


if __name__ == "__main__":
    import datetime
    cfg = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "bz_sync/config.json", encoding="utf-8"))
    creds = json.load(open(cfg["credentials_path"], encoding="utf-8"))
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec="seconds")
    res = run(cfg, creds, now)
    msg = summarize(res)
    print(msg)
    if any(r != "ok" for r in res.values()):
        alert(cfg, msg)
