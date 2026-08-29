# ETF/종목 리스트 자동화 프로젝트 — 세션 진행 요약 (2026-08-27 ~ 08-29)

> 이전 요약(`project_summary.md`)에 이어지는 세션 기록입니다.
> 이 세션에서 확정된 내용은 로컬 `app.py`, GitHub 레포(`hanslee9/etf-holdings`, public),
> Streamlit Community Cloud 배포까지 전부 반영 완료되었습니다.

## 1. 이번 세션에서 해결한 문제

### 1-1. `0198D0` 등 ETF명 깨짐 버그 (완전 해결)

**증상:** `0198D0`(1Q SK하이닉스선물단일종목레버리지) 등 일부 종목의 ETF명이
`ticker\n0198D0 ...\n0198D0 ...` 형태의 지저분한 다중행 텍스트로 반환됨.

**원인 규명 과정:**
1. pykrx 소스코드(`EtxTicker` 클래스) 추적 → 중복 인덱스에서 `.loc[]` 조회 시
   `pandas.Series`가 반환되고, 이를 `str()` 변환하면 증상과 동일한 텍스트가
   나옴을 로컬 재현으로 확인.
2. KRX 공식 API(`getJsonData.cmd`, bld: `MDCSTAT04601`)를 브라우저 개발자도구로
   직접 캡처해 원본 데이터를 대조 → **KRX 원본 데이터 자체는 정상**(중복 없음),
   문제는 pykrx가 ETF+ETN+ELW 세 카테고리를 병합하는 과정에서 발생한 것으로 확정.
3. 2026-05-27 상장된 단일종목 레버리지/인버스 ETF·ETN **18개 종목**(SK하이닉스,
   삼성전자 대상)이 KRX 데이터에서 ELW 목록에도 중복 등재되어 있었음
   (KRX 원본 데이터 결함, pykrx 라이브러리 버그 아님).

**해결:** `get_etf_ticker_name_safe()` 함수 신규 작성. 중복 발생 시 ETF/ETN
카테고리를 ELW보다 우선 선택하도록 처리. `app.py`에 반영 완료.

### 1-2. `489010`(PLUS 글로벌AI인프라) 등 종목명 결측 (자연 결측으로 확정)

5개의 독립적인 소스에서 전부 부재를 확인:
- pykrx (`EtxTicker`, `get_etf_ticker_list`)
- KRX 정보데이터시스템 "전종목 기본정보"(`MDCSTAT04601`) 다운로드
- KRX 정보데이터시스템 "전종목 시세"(`MDCSTAT04301`) 다운로드
- funetf.co.kr (삼성자산운용 운영 서비스) — 여기서는 정상 거래 종목으로 확인됨
- KIS(한국투자증권) Open API 현재가 조회

funetf에서는 실시간 거래되는 것으로 보였으나, 순자산 30억원 규모의 초소형
펀드였던 점을 고려하면 최소 유지 기준 미달로 상장폐지 절차가 진행 중이었을
가능성이 높음. **결론: 자연 결측으로 처리, 코드 수정 불필요.**

### 1-3. yfinance PR/현재가 전량 NaN 버그 (신규 발견 및 해결)

**증상:** 미국 상장 ETF(상위100) 시트를 처음 돌렸을 때, 100종목 전부
`현재가`, `PR 1개월/6개월/YTD/1년`이 NaN으로 나옴.

**원인 규명 과정:**
1. `try/except`로 조용히 넘어가던 로직을 걷어내고 단일 종목(VOO)으로
   재현 → `hist["Close"].iloc[-1]`가 NaN.
2. 원인: `yf.Ticker(ticker).history()`가 반환하는 가장 최근 날짜(당일)
   행의 종가가 장중/미체결로 비어 있는데, 기존 로직이 무조건 마지막
   행을 기준값으로 써서 이 결측을 그대로 전파.

**해결:** `calc_us_stock_metrics()`에 `hist.dropna(subset=["Close"])`를
추가해 유효한 마지막 종가만 사용하도록 수정. **이 수정은 3번 시트뿐 아니라
기존 4, 5, 6번(S&P500/나스닥100/SCHD) 시트에도 공통 적용되어, 예전보다
결측이 줄어들 것으로 예상됨.**

### 1-4. yfinance 100종목 연속 호출 시 대량 실패 (해결)

**증상:** 위 NaN 버그를 고친 뒤에도 100종목 전부 결측 유지.

**원인:** `calc_us_stock_metrics()` 내부의 시가총액 계산 로직이 실패 시
`t.info`(무거운 API 호출)로 폴백하는데, 100종목을 연속 호출하면서 야후
파이낸스 rate limit에 걸려 대량 실패, `except: return {}`로 조용히
삼켜지고 있었음.

**해결:** `calc_us_stock_metrics(ticker, skip_market_cap=True)` 옵션 추가.
3번 시트는 시가총액을 어차피 TradingView 스크래핑값으로 대체하므로
`t.info` 호출 자체를 생략 → rate limit 회피 + 속도 개선.

## 2. 신규 기능: 3번 시트 — 미국 상장 ETF 전체(상위100)

### 2-1. 소스 후보 비교

| 후보 | 로그인 없이 확보 가능한 개수 | 자동 스크래핑 난이도 | 채택 여부 |
|---|---|---|---|
| TradingView (`tradingview-screener` 파이썬 패키지) | 공식 API 응답 자체가 축소됨(7,759건, 정상 약 17,000건 대비 절반 이하) — 코랩/로컬 양쪽에서 동일 현상 확인, IP 문제 아닌 패키지/API 스펙 문제로 결론 | 패키지 설치는 쉬우나 신뢰 불가 | ❌ 폐기 |
| TradingView (정적 웹페이지 `tradingview.com/markets/etfs/funds-usa/`) | **100개** (fetch로 실측 확인, VOO~BIV) | requests + BeautifulSoup으로 스크래핑 가능, 서버사이드 렌더링이라 안정적 | ✅ **채택** |
| stockanalysis.com | 무료 20개(정적 요청 기준, 페이지네이션이 JS로 처리되어 그 이상은 자동화 불가) / 사용자 확인상 브라우저에서는 50개까지 무료, 그 이상 유료($6.58/월, 연간 기준) | 페이지네이션이 클라이언트 JS 기반이라 requests로는 20개 고정, 내부 API 역추적 필요(미시도) | ❌ 보류 (사람이 보기엔 정보량 많지만 자동화엔 부적합) |
| investing.com | 미확인 | 미확인 | ❌ 조사 안 함 (다음 세션 과제) |

### 2-2. `tradingview-screener` 패키지 디버깅 과정 (참고용, 최종 폐기)

1. `pip install tradingview-screener` 설치 → 기본 `Query()`로 ETF 조회 시도했으나
   `type == 'fund'`로 필터링해도 SPAC 신탁 유닛, 우선주 등만 나오고 SPY/QQQ 등
   실제 ETF는 조회되지 않음(`set_tickers('AMEX:SPY')` 등 직접 지정해도 0건).
2. TSLA 등 일반 주식은 정상 조회되는 것으로 보아 fund 타입 자체가 이 API
   엔드포인트에서 배제되는 것으로 의심.
3. 아무 조건 없는 기본 쿼리(`Query().get_scanner_data()`)의 전체 개수(`count`)를
   확인한 결과 7,759건 — 패키지 공식 문서 예시(17,580건)의 절반 이하.
4. 코랩과 로컬(집 PC) 양쪽에서 동일하게 7,758~7,759건이 나와 **세션/네트워크/IP
   문제가 아니라 패키지 또는 API 스펙 자체의 문제로 결론**, 이 접근 폐기.

### 2-3. 최종 채택 로직

- `get_us_etf_top100_raw()`: `requests`로 TradingView 정적 페이지를 가져온 뒤
  `BeautifulSoup`으로 `<table><tbody>`의 `<a>` 태그를 직접 파싱해 티커/종목명을
  분리(주의: `pd.read_html()`은 티커+종목명이 한 셀에 뭉쳐 나와 `VOOVanguard...`
  형태로 잘못 분리되는 문제가 있어 채택하지 않음).
- AUM 문자열(`"1.04 T USD"` 등, 공백 유무가 일정하지 않음)을 정규식으로
  파싱해 백만달러(Mil) 단위 숫자로 변환.
- `process_us_etf_top100_sheet()`: 시가총액은 위 스크래핑값, 현재가/PR/배당수익률은
  `calc_us_stock_metrics(ticker, skip_market_cap=True)`로 채움.
- TradingView 페이지가 이미 AUM 내림차순으로 정렬해 제공하므로 별도 재정렬 불필요.

## 3. 국내 상장 ETF 시트 정렬 변경

기존에는 코드순(가나다순에 가까운 순서)으로 유지했으나, 실사용 시 불편해
KOSPI200/S&P500 등 다른 시트와 동일하게 **시가총액 내림차순**으로 통일.
(`build_domestic_etf_sheet()` 마지막에 `sort_values("시가총액(억원)", ...)` 추가)

## 4. 신규 기능: 종목코드 하이퍼링크

### 4-1. 링크 대상 사이트 조사

| 시트 | 검토 후보 | 최종 채택 | 비고 |
|---|---|---|---|
| 국내 상장 ETF | 네이버증권 vs etfcheck.co.kr | **etfcheck.co.kr** | ETF 전문 사이트로 정보가 더 상세하다고 판단, 실제 상세페이지 URL(`.../mobile/etpitem/069500/basic/개요`)을 사용자가 직접 확인해 종목코드 기반 링크 구조 확정 |
| KOSPI200종목 | 네이버증권 | **네이버증권** | `finance.naver.com/item/main.naver?code=` 패턴 확인 |
| 미국 상장 ETF(상위100) | stockanalysis.com vs investing.com | **stockanalysis.com** | `/etf/{티커}/` 패턴, 개별 종목 페이지 정보량이 풍부해 채택 |
| S&P500/나스닥100/SCHD | stockanalysis.com | **stockanalysis.com** | `/stocks/{티커}/` 패턴 (구성종목이 ETF가 아닌 개별 주식이므로 stocks 경로 사용) |

### 4-2. 검증 방법

코랩에서 `openpyxl`의 `cell.hyperlink` 속성으로 4개 사이트 링크가 실제로
정상 작동하는지 소규모 테스트 엑셀(`link_test.xlsx`)을 만들어 직접 클릭해
확인 완료(국내 ETF/KOSPI200/S&P500/미국ETF 4개 케이스 모두 정상 이동 확인).

### 4-3. 구현

`write_formatted_sheet()`에 `link_func` 매개변수 추가, 시트명 → 링크 생성
함수 매핑(`SHEET_LINK_FUNCS`)을 만들어 `종목코드` 컬럼 셀에 자동으로
하이퍼링크(파란색, 밑줄) 적용.

**남은 확인 사항(다음 세션):** 미국 티커에 점(`.`)이 포함된 경우(예:
`BRK.B`) 기존 로직이 yfinance 조회용으로 `BRK-B`처럼 하이픈 변환해
저장하는데, 이게 stockanalysis.com의 실제 URL 표기와 항상 일치하는지는
소수 종목에 대해 아직 개별 확인하지 못함.

## 5. Git 브랜치를 이용한 백업 워크플로우 도입

오늘 처음으로, 기능 추가 작업 전에 현재 상태를 브랜치로 백업해두는 절차를
도입:

```
git checkout -b before-us-etf-top100
git push origin before-us-etf-top100
git checkout main
```

이후 `main`에서 자유롭게 수정 작업을 진행하고, 문제가 생기면
`before-us-etf-top100` 브랜치로 언제든 복귀 가능한 안전망을 확보.
(로컬 저장소와 GitHub 원격 저장소 양쪽에 보관됨)

## 6. GitHub 저장소 정리

- `app.py`: 오늘 작업한 3개 기능(3번 시트, 국내 ETF 정렬, 하이퍼링크) 전부 반영,
  GitHub 웹 업로드 방식으로 `main`에 직접 커밋.
- `requirements.txt`: `beautifulsoup4>=4.12` 추가 (TradingView 스크래핑에 필요).
- `.gitignore`: `.kis_token_cache.json` 추가 (KIS 접근토큰 캐시 파일이 실수로
  커밋되는 것을 방지).
- `.env.example`과의 병합 충돌 1건 발생 → `git checkout --theirs .env.example`로
  원격(GitHub) 버전 채택 후 해결.
- `README.md`: 3번 시트 반영("미구현" 표기 삭제), 정렬 방식, 하이퍼링크 매핑표,
  오늘 발견한 버그 수정 내역, 다음 세션 과제까지 전면 갱신.

## 7. Streamlit Community Cloud 배포

### 7-1. 배포 절차

`share.streamlit.io`에서 GitHub 저장소(`hanslee9/etf-holdings`, `main`,
`app.py`) 연결 후 배포. `.env` 파일은 배포 환경에 올라가지 않으므로,
Streamlit Cloud의 "Advanced settings → Secrets"에 TOML 형식으로
`KRX_ID`, `KRX_PW`, `KIS_APP_KEY`, `KIS_APP_SECRET`을 별도 입력.

### 7-2. 미해결 이슈: KIS 토큰 발급 403 Forbidden

**증상:** 배포된 앱에서 "KIS 토큰 발급 실패: 403 Client Error: Forbidden
for url: https://openapi.koreainvestment.com:9443/oauth2/tokenP" 발생.
국내 ETF 시가총액만 결측되고 나머지 항목은 정상.

**원인 후보 (미확정, 다음 세션 과제):**
1. **같은 날 중복 발급 시도**: 토큰 캐시(`_KIS_TOKEN_CACHE_PATH`)가 로컬 파일
   기반이라 클라우드 환경(별도 서버)에는 캐시가 없음. 오늘 로컬에서 이미
   토큰을 발급받은 상태에서, 클라우드가 같은 App Key로 재차 신규 발급을
   시도해 "1일 1회 발급 원칙"에 걸렸을 가능성.
2. **접속 IP 제한**: KIS 계정 보안 설정에 등록된 IP만 허용하도록 되어 있고,
   Streamlit Cloud의 서버 IP(해외)가 차단되었을 가능성.

**진단 시도:** KIS API 포털(`apiportal.koreainvestment.com`)에 로그인해
IP 제한 설정을 확인하려 했으나, 포털 로그인 자체가 비밀번호 오류로 반복
실패(전날에도 동일 문제로 비밀번호를 재설정했었음 — 별도 계정 이슈로 보임).
포털 로그인 문제는 이번 세션에서 해결하지 못함.

**임시 조치:** 국내 ETF/KOSPI200(KRX 로그인도 필요)을 제외하고, 미국
관련 4개 시트(3~6번)만 선택해 배포 앱에서 정상 작동 여부 테스트 진행 중.

## 8. 다음 세션 과제 (갱신)

1. **KIS 토큰 403 에러 원인 확정** — 날짜가 바뀐 뒤(자정 이후) 재테스트로
   "같은 날 중복 발급" 가설 검증, 안 되면 KIS API 포털 로그인 문제부터
   해결(고객센터 문의 또는 비밀번호 재설정 재시도) 후 IP 제한 설정 확인
2. KIS API 시가총액 조회 속도 개선 — 병렬 처리 효과 미미, 원인 재조사 필요 (이전 세션 이월)
3. 시가총액 조회 실패분 재시도 로직 검토 (이전 세션 이월)
4. 국내 ETF 분배율 — 여전히 소스 없음, 계속 보류 (이전 세션 이월)
5. 3번 시트(미국 상장 ETF) 개수를 100개 초과로 늘릴 방법 — investing.com 등
   미조사 소스 확인, 또는 stockanalysis.com 유료 API/내부 엔드포인트 조사
6. 미국 티커의 점(`.`) → 하이픈(`-`) 변환이 stockanalysis.com 실제 URL과
   항상 일치하는지 전수 확인 (예: `BRK.B`, `BF.B`)
7. `ref-document/` 폴더 내 세션 요약 문서 전반 최신화 상태 유지
