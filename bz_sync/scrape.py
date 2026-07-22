"""뷰티짱 로그인 + 지점별 휴무/담당자 JSON 수집 (Playwright request API, HTML 파싱 없음)."""

LOGIN_URL = "https://hasys.hairzzang.com/"
BASE = "https://hasys.hairzzang.com"
BAN_URL = BASE + "/CRM.reservation/StatusBoardV2-AjaxReservationBanList"
RV_URL = BASE + "/CRM.reservation/StatusBoardV2-AjaxReservationList"
REQ_TIMEOUT = 60000  # ms


def login(page, creds: dict) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    page.fill("#strShopCode", creds["shop_code"])
    page.fill("#strId", creds["user_id"])
    page.fill("#strPass", creds["password"])
    # doLoginCheck()가 비번 클라이언트 해싱 후 postback을 수행한다.
    # #btnSubmit을 직접 click하면 해싱을 건너뛰어 서버가 500(ErrorPage)로 튕김.
    page.evaluate("doLoginCheck()")
    page.wait_for_timeout(4000)  # 세션 쿠키 확립


def _last_day(year: int, month: int) -> int:
    import calendar
    return calendar.monthrange(year, month)[1]


def _week_ranges(year: int, month: int) -> list[tuple[str, str]]:
    """월을 7일 단위 구간으로 분할. RV(예약목록) 월범위 단건은 응답이 커(3MB+)
    서버 30초 한계에서 간헐적으로 빈 응답을 주므로, 주 단위로 나눠 안정적으로 수집."""
    last = _last_day(year, month)
    out: list[tuple[str, str]] = []
    d = 1
    while d <= last:
        e = min(d + 6, last)
        out.append((f"{year:04d}-{month:02d}-{d:02d}", f"{year:04d}-{month:02d}-{e:02d}"))
        d = e + 1
    return out


def _post_json(req, url: str, body: dict, retries: int = 3):
    """POST 후 JSON 파싱.
    - 정상: 파싱된 값 반환.
    - 빈 문자열 응답(status 200 + 0바이트): 서버가 '해당 지점/월 데이터 없음'일 때
      주는 정상 신호 → 재시도 후에도 계속 비면 []([] = 무데이터)로 간주.
    - 비정상(HTML 에러 등 파싱 불가): 재시도 후에도 실패하면 None(진짜 오류)."""
    saw_empty = False
    for _ in range(retries):
        resp = req.post(url, form=body, timeout=REQ_TIMEOUT)
        text = resp.text()
        if not text:
            saw_empty = True
            continue
        try:
            return resp.json()
        except Exception:
            continue
    return [] if saw_empty else None


def fetch_branch(page, oid_store: str, year: int, month: int) -> tuple[list, list]:
    """(ban_rows, rv_rows) 반환.
    - BAN(휴무·정본): 월범위 단건. 실패하면 RuntimeError(그 달 휴무를 못 얻으므로 지점 실패 처리).
    - RV(담당자명 소스): 주 단위 구간을 순회해 행을 이어붙임(월 전체 커버리지).
      한 구간이 끝내 비면 스킵(다른 구간이 이름을 보강)."""
    req = page.context.request
    ds = f"{year:04d}-{month:02d}-01"
    de = f"{year:04d}-{month:02d}-{_last_day(year, month):02d}"
    ban = _post_json(req, BAN_URL, {
        "seloidStore": str(oid_store), "strDateS": ds, "strDateE": de, "viewStaff": "ALL",
    })
    if ban is None:
        raise RuntimeError(f"BAN empty/invalid for store {oid_store} {year}-{month:02d}")

    rv_rows: list = []
    for s, e in _week_ranges(year, month):
        rows = _post_json(req, RV_URL, {
            "seloidStore": str(oid_store), "strDateS": s, "strDateE": e, "viewStaff": "ALL",
        })
        if rows:
            rv_rows.extend(rows)
    return ban, rv_rows
