"""오케스트레이터: 지점 순회 → JSON 수집 → 집계 → Firebase write. 부분성공·실패알림."""
import json
import sys

from bz_sync.scrape import login, fetch_branch
from bz_sync.banparse import parse_bans, parse_staff_names
from bz_sync.names import resolve_bans
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
    with open(config["branch_stores_path"], encoding="utf-8") as f:
        stores = json.load(f)
    results: dict[str, str] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        login(page, creds)
        for branch, oid in stores.items():
            if branch.startswith("_"):
                continue
            branch_failed = False
            failed_month_error = None
            for (y, m) in _months(now_iso):
                try:
                    ban, rv = fetch_branch(page, oid, y, m)
                    bans = resolve_bans(parse_bans(ban, config["half_reasons"]), parse_staff_names(rv),
                                        config["system_accounts"], config["name_map"])
                    status = write_branch(base, y, m, branch, build_payload(bans, now_iso))
                    if status >= 400:
                        raise RuntimeError(f"firebase {status}")
                except Exception as e:
                    branch_failed = True
                    if failed_month_error is None:
                        failed_month_error = e
            if branch_failed:
                results[branch] = f"fail:{type(failed_month_error).__name__}"
            else:
                results[branch] = "ok"
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
    with open(sys.argv[1] if len(sys.argv) > 1 else "bz_sync/config.json", encoding="utf-8") as f:
        cfg = json.load(f)
    with open(cfg["credentials_path"], encoding="utf-8") as f:
        creds = json.load(f)
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec="seconds")
    res = run(cfg, creds, now)
    msg = summarize(res)
    print(msg)
    if any(r != "ok" for r in res.values()):
        alert(cfg, msg)
