# 뷰티짱 정찰 결과 (Task 1) — 2026-07-22

라이브 접속(본사 계정)으로 확인. 자격증명 값은 본 문서·로그·코드에 기록하지 않음.

## 로그인
- URL: `https://hasys.hairzzang.com/` (ASP.NET WebForms, `__VIEWSTATE`).
- 필드: `#strShopCode`(샵코드) / `#strId`(아이디) / `#strPass`(비밀번호), 제출 `#btnSubmit` 또는 `doLoginCheck()`.
- 세션 쿠키 기반. 로그인 후 `CRM.LoadPage`(프레임셋) 접근 가능.
- **주의:** 프레임셋의 `frame_push`(`Library/Api/Controller/Push.aspx`)가 long-poll → 페이지 load 이벤트가 끝나지 않음.
  Playwright는 `wait_until="domcontentloaded"` + 타임아웃 catch로 넘기고, 이후 frame 단위로 조작.

## 프레임 구조 (CRM.LoadPage)
- `frame_main` → `/CRM.Main/defaultNew` (상단 메뉴 + 콘텐츠 로더 `jHeader.doMenuLoad(...)`)
- `frame_config`, `frame_push`(long-poll)

## 휴무 소스 후보 조사 결과
| 화면 | URL / 엔드포인트 | 판정 |
|---|---|---|
| 근태입력 | `/staff/diligence/default.aspx?page=Diligence&oidTopMenu=30&oidFirstTopMenu=4` | ✗ 월그리드 아님. 일별 출퇴근 입력표(담당자번호·이름·출근/퇴근기준·시간·메모) |
| 근태현황 | `POST /CRM.staff/Diligence-ListByDiligenceAjaxList` | △ 월간 **집계**(근무·결근·**휴무일수**…). `ddlOfficeGubun` 현지점/전지점. 날짜별 아님 |
| **휴무캘린더** | `/CRM.regist/reservation-default?page=calendar&oidTopMenu=332&oidFirstTopMenu=9` (또는 `POST /CRM.Regist/Reservation-HolidayCalendar`) | ✅ **정본 후보.** 월 달력, 날짜별 `div.day_View[date]` |
| 매장휴무일 | `/CRM.regist/reservation-default?page=holiday` | 매장 단위 휴무(직원 아님) |
| 예약현황판 | `/CRM.Reservation/StatusBoardV2` | 당일 디자이너 스케줄+OFF. 날짜 순회 필요(백업) |

## 휴무캘린더 DOM 구조 (확인)
- 콘텐츠 프레임 URL: `…?page=calendar&oidTopMenu=332&oidFirstTopMenu=9`
- 달력 표: 5주 × 7일 = 35개 `td`, 각 셀에 날짜 div:
  ```html
  <div class="day_View" date="2026-07-03">
    <div class="date_Box"><span class="date_Txt">3</span></div>
    <!-- 해당 날짜에 등록된 휴무 직원 엔트리가 여기에 추가됨 (본사 컨텍스트에선 비어있음) -->
  </div>
  ```
  - 전월/익월 잉여 날짜는 `<span class="disable">`, 당월은 `<span class="date_Txt">`.
  - **파서는 `div.day_View[date]`를 키로 잡고, 그 안의 휴무 직원 엔트리를 읽는다.**
    날짜는 `date` 속성(`YYYY-MM-DD`)에서 직접 취득 → 열 순서 계산 불필요.

## 지점 컨텍스트 (중요)
- 현재 계정 로그인 시 컨텍스트 = **끌리메(본사)** (`span.shopNeme` = "끌리메(본사)").
- **본사엔 디자이너가 없어 모든 스케줄/휴무 화면이 비어있음.** → 반드시 **신사점 등 지점으로 전환**해야 실데이터가 보임(사용자 지시와 일치).

## ⚠️ 미해결(라이브로 마저 확정 필요 — 신사점 전환 후)
1. **지점 전환 방법**: CRM 앱 내 인라인 드롭다운/함수로는 못 찾음(`jHeader`에 shop-switch 함수 없음, DOM에 지점명 옵션 없음).
   사용자가 말한 "예약 오른쪽의 지점 선택"의 실제 위치·동작(팝업? 그룹포털? 별도 URL?)을 사용자와 함께 확인해야 함.
2. **populated day_View 마크업**: 신사점 전환 후, 휴무가 등록된 날짜 셀의 실제 HTML(직원명 엔트리 클래스/구조)을 캡처해
   `bz_sync/tests/fixtures/offdays_sinsa_current.html`로 저장 → 파서(Task 2) `_extract_off_staff()` 확정.

## 기타
- 엑셀 내보내기 존재: `fnExcelDownloadAuth()` → `/include/Common/ExcelDownlaodAuth.aspx`(팝업).
- 일부 JSON 엔드포인트: `POST /CRM.include/Left-ReservCountByStatusAjax` → `{"rv_cnt":0,"wait_cnt":0}`.
- 발견된 시스템 계정(휴무 파싱 시 제외 대상, 근태현황 담당자 목록에서): 결제변경, 소멸, 매장, 환불, 워크인, 전일취소, 당일취소, 대기, 유료.
