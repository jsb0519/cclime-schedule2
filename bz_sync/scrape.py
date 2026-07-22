"""뷰티짱 로그인 + 지점별 휴무/담당자 JSON 수집 (Playwright request API, HTML 파싱 없음)."""

LOGIN_URL = "https://hasys.hairzzang.com/"
BASE = "https://hasys.hairzzang.com"
BAN_URL = BASE + "/CRM.reservation/StatusBoardV2-AjaxReservationBanList"
RV_URL = BASE + "/CRM.reservation/StatusBoardV2-AjaxReservationList"


def login(page, creds: dict) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    page.fill("#strShopCode", creds["shop_code"])
    page.fill("#strId", creds["user_id"])
    page.fill("#strPass", creds["password"])
    page.eval_on_selector("#btnSubmit", "el => el.click()")
    page.wait_for_timeout(4000)  # 세션 쿠키 확립


def _last_day(year: int, month: int) -> int:
    import calendar
    return calendar.monthrange(year, month)[1]


def fetch_branch(page, oid_store: str, year: int, month: int) -> tuple[list, list]:
    body = {
        "seloidStore": str(oid_store),
        "strDateS": f"{year:04d}-{month:02d}-01",
        "strDateE": f"{year:04d}-{month:02d}-{_last_day(year, month):02d}",
        "viewStaff": "ALL",
    }
    req = page.context.request
    ban = req.post(BAN_URL, form=body).json()
    rv = req.post(RV_URL, form=body).json()
    return ban, rv
