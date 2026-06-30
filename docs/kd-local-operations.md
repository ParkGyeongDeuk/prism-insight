# kd-local 운영 기록 및 다음 작업 가이드

이 문서는 `kd-local` 브랜치에서 사용자의 로컬 PC 기준으로 PRISM-INSIGHT를 국내 모의투자 중심으로 운영하기 위해 적용한 차이점과 다음 작업자가 반드시 확인해야 할 내용을 정리한다. 새 Codex context에서 작업을 이어갈 때는 `AGENTS.md`, `CLAUDE.md`, `docs/SETUP_ko.md`와 함께 이 문서를 먼저 읽는다.

## 운영 목표

- 로컬 Docker 환경에서 국내 주식 모의투자를 자동 운영한다.
- 원본 저장소와의 sync 충돌을 줄이기 위해 원본 구조와 핵심 로직 변경은 최소화한다.
- 실계좌/실전투자는 별도 점검 전까지 활성화하지 않는다.
- 매매 자동화는 항상 KIS 모의투자 계좌와 추적 DB 정합성을 확인하면서 진행한다.

## 브랜치와 기본 원칙

- 작업 브랜치: `kd-local`
- 사용자는 개인 fork에서 작업한다.
- 원본 업데이트는 사용자가 `main`에서 sync하고 충돌 여부를 확인하는 방식으로 관리한다.
- Codex는 변경이 충분히 검증된 시점에 한국어 커밋 메시지로 커밋한다. push는 보통 사용자가 직접 한다.
- 실제 credential, token, 계좌 정보는 절대 커밋하지 않는다.

## 운영문서 기록 기준

`docs/kd-local-operations.md`는 다음 작업자가 반드시 기억해야 할 로컬 운영 차이, 의사결정, 검증 기준을 남기는 문서로 유지한다.

- 기록한다: 원본과 다른 로컬 운영 정책, feature gate/LIVE 전환 판단 기준, merge 시 재검토할 항목, 장애 대응에 필요한 특이사항.
- 기록하지 않는다: 매번 같은 형태로 반복되는 빌드/컨테이너 교체 결과, 일회성 상태 스냅샷, 운영 판단에 큰 도움이 되지 않는 단순 확인 로그.
- 반복 배포 이력은 특별한 위험이나 의사결정 변경이 있을 때만 요약하고, 일반적인 재빌드/재시작 성공 여부는 커밋 메시지나 대화 기록으로 충분하다고 본다.

## 보고서 입력 기준

- 매매 판단과 Telegram 요약은 원본 `.md` 보고서를 LLM 입력 기준으로 사용한다.
- `.md` 안의 base64 차트 이미지는 LLM 입력 전에 제거한다. 차트 이미지를 판단에 쓰려면 별도 vision gate로 명시적으로 검토한다.
- PDF는 사용자 제공용 산출물로 유지하며, 오래된 수동 호출을 위해 PDF 텍스트 추출 fallback만 남긴다.
- kd-local은 `PRISM_GENERATE_PDF_REPORTS=false`, `PRISM_SEND_PDF_REPORTS=false`로 PDF 생성과 Telegram PDF 첨부 전송을 모두 끈다. 매매 판단과 Telegram 요약은 `.md` 기반이라 영향을 받지 않는다.
- PDF가 다시 필요하면 `PRISM_GENERATE_PDF_REPORTS=true`로 생성만 켤 수 있고, 첨부 전송까지 필요할 때만 `PRISM_SEND_PDF_REPORTS=true`를 함께 켠다.
- Telegram 요약 파일명 메타데이터는 `.md`/`.markdown`/`.pdf` 모두 같은 규칙으로 인식해야 한다. `.md` 전환 후에도 생성 파일은 `{종목코드}_{종목명}_telegram.txt` 형태로 유지되어야 전송 단계에서 누락되지 않는다.

## 절대 커밋하지 않을 파일과 데이터

다음 파일은 로컬 운영/비밀 정보로 취급한다.

- `.env`
- `mcp_agent.secrets.yaml`
- `trading/config/kis_devlp.yaml`
- ChatGPT OAuth token 저장소
- KIS access token/cache 파일
- 생성된 로그, PDF, JSON 결과물
- `stock_tracking_db.sqlite` 등 SQLite DB

문서나 커밋 메시지에도 실제 API key, bot token, 계좌번호 전체, 비밀번호를 남기지 않는다. 계좌 표기는 필요할 때만 마스킹된 라벨을 사용한다.

## 로컬 Docker 운영 구조

로컬 운영은 기본 `docker-compose.yml` 위에 `docker-compose.local.yml`을 덮어씌우는 방식이다.

사용자가 직접 빌드, 실행, 중지, 로그 확인, 컨테이너 접속, 수동 실행, 테스트를 할 때는 `docs/kd-local-docker-guide.md`를 우선 참고한다. 이 문서는 현재 kd-local compose 구조와 cron 운영 방식을 기준으로 작성된 실무 명령 가이드다.

`.env`에는 다음 값이 필요하다.

```env
COMPOSE_FILE=docker-compose.yml:docker-compose.local.yml
PRISM_ENABLE_CRON=true
PRISM_OPENAI_AUTH_MODE=chatgpt_oauth
PRISM_OAUTH_CALLBACK_HOST=0.0.0.0
PRISM_KR_MAX_SLOTS=5
PRISM_KR_TOTAL_BUDGET=2000000
PRISM_KR_CASH_RESERVE=400000
PRISM_GENERATE_PDF_REPORTS=false
PRISM_SEND_PDF_REPORTS=false
```

`docker-compose.local.yml`의 역할:

- 국내 로컬 운영용 환경변수를 컨테이너에 전달한다.
- `trading/config/kis_devlp.yaml`을 컨테이너에 bind mount한다.
- ChatGPT OAuth token을 Docker volume `prism-auth`에 보존한다.
- `docker/crontab.kd`를 컨테이너의 `/app/prism-insight/docker/crontab`으로 mount한다.
- OAuth callback port `1455`를 `127.0.0.1`에만 노출한다.

## 로컬 테스트 의존성

운영 의존성인 `requirements.txt`와 Dockerfile은 원본 merge 부담과 운영 이미지 변화를 줄이기 위해 그대로 둔다.

로컬 검증이 필요할 때만 `requirements-dev.txt`를 컨테이너에 설치한다.

```bash
docker compose exec -T prism-insight pip install -r requirements-dev.txt
```

현재 dev 의존성은 `pytest`, `pytest-asyncio`만 둔다. core/trading 런타임 모듈에는 영향을 주지 않는 테스트 실행 도구로만 취급한다.

## 국내 모의투자 자금 설정

현재 운용 가정:

- 총 운용한도: 2,000,000원
- 현금 예비금: 400,000원
- 실제 투자 가능 한도: 1,600,000원
- 최대 보유 슬롯: 5개
- 슬롯당 매수 금액: 약 320,000원

관련 코드:

- `stock_tracking_agent.py`
  - `PRISM_KR_MAX_SLOTS`를 읽어 최대 슬롯을 로컬에서 줄일 수 있게 했다.
  - 상한은 원본 기본값 `MAX_SLOTS = 10`을 넘지 않는다.
  - `PRISM_KR_TOTAL_BUDGET`, `PRISM_KR_CASH_RESERVE`를 읽어 투자 가능 한도를 계산한다.
  - 다음 슬롯 진입 시 `(현재 슬롯 + 1) * buy_amount_krw`가 투자 가능 한도를 넘으면 매수를 차단한다.

검증 테스트:

- `tests/test_stock_tracking_max_slots.py`

주의:

- 슬롯 5개는 보유 종목 수의 상한이다.
- 종목 가격이 슬롯당 매수 금액보다 높으면 매수 가능 수량이 0주가 되어 주문이 실패할 수 있다.
- 2026-06-23 오전 자동 실행에서 `034730`, `000660`은 AI 진입 판단이 나왔지만, 현재가가 320,000원을 초과해 실제 매수는 0건이었다. 이는 현재 자금 설정 기준으로 정상적인 제한이다.

## cron 운영

현재 국내 자동 운영 cron은 `docker/crontab.kd`에서 관리한다.

스케줄:

- `03:00` 매일: 로그/보고서 정리
- `03:30` 일요일: trading memory 압축
- `07:00` 평일: 국내 종목 코드/이름 갱신
- `09:30` 평일: 국내 오전 분석 및 모의투자 판단
- `15:40` 평일: 국내 오후 분석 및 모의투자 판단
- `17:00` 평일: 성과 추적 batch

중요한 로컬 차이:

- 각 cron 작업은 실행 직전에 `.env`를 로드한다.
- 이유: Docker 컨테이너의 일반 환경에는 `PRISM_KR_MAX_SLOTS=5` 등이 있어도 cron 프로세스에는 누락될 수 있다.
- 이 보강이 없으면 텔레그램 포트폴리오가 `0/10`처럼 원본 기본 슬롯 기준으로 표시되거나, 예산 제한이 자동 실행 경로에서 빠질 위험이 있다.

관련 커밋:

- `3e38855 운영: 국내 모의투자 유지보수 일정 복원`
- `fb30d9c 운영: 로컬 cron 실행 시 환경 설정 로드`

운영 확인 명령:

```bash
docker compose ps
docker compose exec -T prism-insight service cron status
docker compose exec -T prism-insight crontab -l
docker compose exec -T prism-insight bash -lc 'cd /app/prism-insight && set -a && . /app/prism-insight/.env && set +a && python3 -c "from stock_tracking_agent import StockTrackingAgent; print(StockTrackingAgent._resolve_max_slots())"'
```

마지막 명령은 `5`가 나와야 한다.

## KIS 설정과 안전 상태

`trading/config/kis_devlp.yaml`은 로컬 비밀 파일이다. 현재 의도는 국내 KIS 모의투자 계좌 운영이다.

필수 확인 사항:

- `default_mode: demo`
- `auto_trading: true`는 사용자가 명시적으로 자동 모의투자를 시작하기로 한 뒤에만 사용한다.
- 실전 key는 모의투자 key와 다르다. 모의투자 key는 사용자가 paper app key임을 확인했다.
- 실전투자 전환은 이 문서의 범위를 벗어난다. 별도 checklist와 사용자 재승인이 필요하다.

적용된 안전 보강:

- KIS app key 접두어를 공개 계약으로 가정하지 않고 불투명 값으로 취급한다.
- 국내 휴장일에는 주문을 차단한다.
- 모의투자 미체결 조회와 취소 식별자를 보완했다.
- 2026-06-26 오후 실행에서 KIS 모의투자 장후 예약주문 매수/매도가 모두 `IGW00009`로 실패했고, 미체결 조회에서도 접수 여부를 검증할 수 없었다. kd-local 모의투자(`mode=demo`)에서는 예약주문 시간대 주문을 제출하지 않고 실패 처리한다. 정규장과 장후 단일가 구간은 기존 주문 경로를 유지한다.
- 예약 매수 API가 실패처럼 응답해도 실제 미체결 매수 주문이 생기는 경우를 대비한 사후 보정 로직은 남겨두되, kd-local 모의투자 기본 경로에서는 예약주문 제출 전 차단된다. 실전(`mode=real`) 예약주문은 별도 검증 전까지 운영 전환하지 않는다.
- 예약/미체결 매수 주문을 추적 DB에 복구할 때는 `scenario.order_status = reserved_open`으로 구분하고, 실제 KIS 보유로 전환되기 전에는 매도 판단 대상에서 제외한다.
- 매수 성공 후 추적 DB의 종목명과 매수가는 분석 보고서/trigger 기준값보다 KIS 주문 결과와 사후 포트폴리오 조회값을 우선한다. 장중 시장가 매수는 분석 시점 가격과 실제 평균단가가 달라질 수 있으므로, DB `stock_holdings.buy_price`는 가능한 한 KIS 평균단가와 맞춰야 한다.
- 매도는 KIS 브로커 주문 성공 후에만 추적 DB의 `stock_holdings` 삭제와 `trading_history` 확정을 수행한다. 브로커 실패/조회 실패 시에는 현재가만 갱신하고 보유 row를 유지한다.
- LLM 인증/쿼터/응답 파싱 실패로 매수 시나리오가 생성되지 않은 경우에는 안전하게 매매를 건너뛰되, `watchlist_history`/`analysis_performance_tracker`에는 정상 분석 결과처럼 저장하지 않는다.
- 주문 전후에 KIS 계좌 상태와 추적 DB 정합성을 확인한다.
- 브로커 조회 실패를 단순 빈 포트폴리오로 오인하지 않도록 방어한다.

관련 커밋:

- `1ffcc79 수정: KIS 앱 키 접두어를 불투명 값으로 처리`
- `203fc03 안전: 국내 주식 휴장일 주문 차단`
- `30c5a48 수정: 모의투자 미체결 조회와 취소 식별자 보완`
- `b2d104a 안전: KIS 주문과 추적 DB 정합성 검증 강화`

## KRX 로그인 보강

KRX Data 사이트 로그인 시 이미 로그인된 계정이라는 확인 modal이 뜰 수 있다. 이 경우 기존 계정 로그아웃 후 새 로그인 확인을 눌러야 한다.

적용된 보강:

- 중복 로그인 확인 modal 처리
- KRX 로그인 흐름의 page navigation은 `domcontentloaded` 기준으로 처리한다. KRX 페이지가 `load`/`networkidle` 상태로 안정화되지 않는 날에도 로그인 폼 접근, session cookie 확인, 실제 인증 실패 여부 판단은 계속 진행하기 위함이다.
- 로그인 전 기존 session logout 정리는 best-effort 호출로 처리한다. KRX logout URL이 안정화되지 않아도 오전/오후 분석 전체가 60초 단위 재시도에 묶이지 않게 하기 위함이다.
- 최근 검증된 KRX session의 검증 요청이 timeout/connection error로 실패하면, 명시적인 `LOGOUT`/HTML 응답이 아닌 한 즉시 session 파일을 삭제하지 않고 짧은 grace window 안에서는 기존 session을 유지한다.
- KRX session cookie 재발급 및 저장
- 로그인 재시도 중 cookie 값은 로그에 노출하지 않도록 처리

관련 커밋:

- `f33ed83 수정: KRX 중복 로그인 확인 모달 처리`

## AI/API 구성

현재 의도한 역할 분담:

- KRX/KIS: 가격, 거래량, 수급, 계좌/주문 데이터
- Firecrawl: 국내 기업 원문 뉴스와 기업 정보 수집 보조
- Perplexity: 시장 원인, 거시경제, 업종 비교 등 검색형 분석
- GPT-5.4 mini: 수집 데이터를 통합한 최종 분석과 판단
- ChatGPT OAuth proxy: OpenAI API key 대신 ChatGPT Plus/Pro 구독 기반 호출

수동 실행 원칙:

- 국내 분석/매매 판단 수동 실행은 가능하면 `stock_analysis_orchestrator.py --mode morning/afternoon` 경로를 사용한다.
- 보유 종목 tracking agent를 임시 스크립트로 직접 호출할 때는 `MCPApp`/agent 생성 전에 ChatGPT OAuth proxy를 먼저 초기화한다. 그렇지 않으면 placeholder 키가 OpenAI API로 직접 전달되어 `401 invalid_api_key`가 발생할 수 있다.

Perplexity key는 사용자가 발급 및 설정했다. `.env`와 필요한 secret 파일 모두에 들어갈 수 있지만 실제 값은 문서화하지 않는다.

과거에는 Perplexity 미설정 상태에서도 분석이 가능한 대체 경로를 추가했다. 현재는 Perplexity 사용을 기본 운영으로 본다.

관련 커밋:

- `c891692 기능: Perplexity 미설정 시 분석 대체 경로 추가`
- `e4077c3 수정: Docker MCP 실행과 OAuth 도구 호출 호환성 보완`

## 2026-06-23 첫 자동 모의투자 실행 결과

상태:

- 09:30 국내 morning cron 실행 시작
- 종목 분석 PDF와 실시간 포트폴리오가 Telegram 채널에 전송됨
- Full pipeline은 10:12경 완료
- KRX session 만료가 있었지만 자동 재로그인으로 복구됨
- 차트 생성 중 KRX timeout 로그가 있었지만 전체 pipeline은 계속 진행됨
- AI는 일부 종목에 `Enter` 판단을 냈으나, 고가 종목이라 매수 가능 수량이 0주였다.

최종 확인:

- KIS 모의계좌 보유종목: 0건
- KIS 미체결 주문: 0건
- DB `stock_holdings`: 0건
- DB `trading_history`: 0건

텔레그램 포트폴리오가 `0/10`으로 표시된 문제:

- 원인: cron 실행 경로에서 `PRISM_KR_MAX_SLOTS`가 로드되지 않아 기본값 10을 사용했을 가능성이 높다.
- 조치: `docker/crontab.kd`의 각 job이 `.env`를 로드하도록 수정하고 현재 컨테이너 crontab에도 재설치했다.
- 기대 결과: 다음 포트폴리오 메시지는 `0/5개` 기준이어야 한다.

## 2026-06-23 v2.15.0 병합 기준

`main` v2.15.0을 `kd-local`에 병합할 때의 로컬 운영 원칙:

- `cores/llm/openai_responses_llm.py` 충돌은 원본 v2.15.0의 stateless multi-turn 방식으로 해결한다.
  - ChatGPT OAuth/Codex 경로에서는 `previous_response_id`가 strip되므로, 매 턴 `function_call`과 `function_call_output`을 누적 input으로 재전송하는 방식이 기준이다.
- `tools/feature_status.py`, OAuth quota monitor, 비전 관련 신규 파일은 받아도 된다.
- 단, 로컬 국내 모의투자 운영에서는 별도 승인 전까지 다음 기능을 cron/env로 활성화하지 않는다.
  - Loop A/B/C live mode: `LOOP_A_LIVE=true`, `LOOP_B_LIVE=true`, `LOOP_C_LIVE=true`
  - 비전 분석: `PRISM_FEATURE_VISION=on`
  - 비전 매수품질 live 영향: `PRISM_VISION_SHADOW=false`
- 원본 v2.15.0 구현도 신규 기능이 merge만으로 실제 주문/매매 판단에 바로 영향 주지 않도록 기본값을 OFF/SHADOW로 둔다.
  - Loop A/B/C는 각 `*_LIVE`가 기본 `false`라 실제 sell/amend/cancel 경로 대신 "would" 로그와 loop table 기록만 수행한다.
  - 비전 매수품질 검사는 `PRISM_FEATURE_VISION` 기본값이 `off`이며, 켜더라도 현재는 `[BUY_QUALITY][SHADOW]` 로그만 남기고 매수 판단에 주입하지 않는다.
- `docker/crontab.kd`에는 기존 국내 배치, cleanup, compression, performance tracker만 유지한다.
- v2.15.0 병합 후에는 `tools/feature_status.py`로 실제 런타임 상태를 확인하되, Loop/vision이 OFF 또는 미스케줄/SHADOW인 상태를 정상으로 본다.
- 다음 원본 버전을 merge할 때는 `tools/feature_status.py`, `cores/analysis.py`, `tools/loop_a_hardstop.py`, `tools/loop_b_trend_exit.py`, `tools/loop_c_fill_chaser.py`의 기본 게이트가 계속 OFF/SHADOW인지 먼저 확인한다.

병합 후 컨테이너 반영:

- 병합 commit 이후 `docker compose build prism-insight`와 `docker compose up -d --force-recreate prism-insight`로 이미지를 재빌드하고 컨테이너를 교체했다.
- 교체 전 실행 중인 분석/주문 관련 Python 프로세스가 없음을 확인했다.
- 교체 후 확인 결과:
  - 컨테이너 상태: healthy
  - `tools/feature_status.py`가 컨테이너에 존재
  - `cores/llm/openai_responses_llm.py`는 stateless multi-turn 구현 반영
  - crontab은 `docker/crontab.kd` 기준으로 설치됨
  - `StockTrackingAgent._resolve_max_slots()` 결과는 `5`
  - feature status는 OAuth `LIVE`, Loop A `OFF`, Loop B/C `미스케줄`, vision 계열 `OFF`

## Loop A/B/C SHADOW 관측 운영

원본 v2.15.0의 Loop A/B/C는 기본 SHADOW이므로, 국내 모의투자에서 먼저 관측 데이터를 쌓기로 했다.

적용 기준:

- 대상은 KR 모의투자 계좌만으로 제한한다. US loop는 로컬 운영 범위 밖이므로 cron에 올리지 않는다.
- `LOOP_A_LIVE`, `LOOP_B_LIVE`, `LOOP_C_LIVE`는 설정하지 않는다.
- 실제 주문, 정정, 취소, 매매 판단 변경 없이 "would" 로그와 loop table 기록만 관찰한다.
- KIS 조회 부하와 기존 09:30/15:40 배치와의 겹침을 줄이기 위해 원본 예시보다 보수적인 staggered 주기로 실행한다.

현재 `docker/crontab.kd`의 SHADOW 관측 스케줄:

- Loop C 미체결 추격 관측: 평일 09~15시, `3-53/10`분
- Loop A 고빈도 하드스톱 관측: 평일 09~15시, `5-55/10`분
- Loop B 추세이탈 관측: 평일 09~15시, `7-52/15`분
- Loop B 종가 확인 관측: 평일 15:10~15:20, 5분 간격, `LOOP_B_CLOSE_WINDOW=true`

관찰할 로그:

```bash
tail -200 logs/loop_a_shadow_$(date +%Y%m%d).log
tail -200 logs/loop_b_shadow_$(date +%Y%m%d).log
tail -200 logs/loop_c_shadow_$(date +%Y%m%d).log
```

자료가 쌓인 뒤에는 SHADOW 시그널과 실제 결과를 비교해 LIVE 전환 여부를 판단한다.

- Loop A/B 매도 시그널은 `WOULD SELL` 발생 시각, 당시 가격, 실제 기존 로직의 이후 보유/매도 결과를 비교한다.
- Loop A는 급락 방어 목적이므로, SHADOW 매도 시점 이후 추가 하락을 줄였는지와 직후 반등으로 인한 조기 매도 오판이 많았는지를 본다.
- Loop B는 추세 이탈 목적이므로, `breach_streak`가 쌓인 뒤 실제 추세 하락이 이어졌는지와 휩쏘 비율이 과도한지를 본다.
- Loop C는 미체결 주문 기준으로 `WOULD AMEND`/`WOULD CANCEL`이 실제 체결률, 체결가, 불필요한 추격 주문 감소에 도움이 됐을지를 본다.
- 비교 대상 DB 테이블은 `loop_a_inflight_orders`, `loop_b_position_state`, `loop_b_inflight_orders`, `loop_c_chase_log`이며, 필요하면 별도 분석 스크립트로 SHADOW 시그널과 실제 KIS/DB 결과를 매칭한다.
- LIVE 전환 검토 전에는 단순 날짜 수보다 실제 시그널 수를 우선한다. 보유 종목이나 미체결 주문이 없어 시그널이 없던 기간은 검증 표본으로 보지 않는다.

LIVE 전환은 자동으로 하지 않는다. 최소 첫 보유 종목 발생 후 며칠간 SHADOW 로그를 보고, KIS/DB/Telegram 정합성 확인이 끝난 뒤 Loop A부터 별도로 판단한다. Loop B는 휩쏘 검증이 필요하므로 더 긴 관찰 기간을 둔다. Loop C는 정정/취소 TR 검증 부담이 가장 크므로 가장 마지막에 검토한다.

## 앞으로 꼭 관찰해야 할 항목

다음 항목은 아직 장기간 검증이 끝난 것이 아니므로, 새 context에서 작업을 이어갈 때 우선 확인한다.

1. 다음 Telegram 포트폴리오 메시지의 보유 슬롯 표시
   - 기대값: `현재 보유: n/5개`
   - `n/10개`로 나오면 cron 실행 경로에서 `.env` 로드가 다시 빠졌거나 다른 메시지 경로가 사용된 것이다.

2. 실제 첫 매수 발생 시 KIS, DB, Telegram 정합성
   - KIS 앱 보유수량과 `stock_holdings` row가 일치해야 한다.
   - `trading_history`는 실제 매도 완료 후 기록되는 흐름인지, 매수 시 별도 기록이 있는지 코드 기준으로 확인한다.
   - 매수 성공 로그가 있는데 DB row가 없으면 위험 상태로 보고 추가 매매를 멈춘 뒤 원인을 확인한다.

3. 미체결 주문 처리
   - KIS 미체결 주문이 남았을 때 프로그램이 보유/미보유 상태를 어떻게 판단하는지 확인한다.
   - 미체결이 있는데 DB만 먼저 반영되거나, 반대로 체결됐는데 DB가 비어 있는 상황을 가장 조심한다.

4. 슬롯당 320,000원 한도와 고가 종목 반복 탈락
   - 고가주만 계속 AI 진입 후보로 선정되면 실제 매수가 계속 0건일 수 있다.
   - 이 현상이 반복되면 "매수 가능 가격 필터", "슬롯 수 조정", "종목당 금액 조정" 중 하나를 사용자와 논의한다.
   - 단, 바로 로직을 바꾸지 말고 최소 며칠의 로그와 후보 종목 가격대를 먼저 본다.

5. 오후 15:40 자동 실행
   - 오전 실행만 확인된 상태에서 끝내지 않는다.
   - 오후 job이 보고서 생성, 보유 점검, 매도/보유 판단, Telegram 전송까지 정상 완료되는지 확인한다.

6. 17:00 성과 추적 batch
   - 첫 매수/매도 이후 `performance_tracker_batch.py`가 정상 실행되는지 확인한다.
   - 성과 tracking 테이블에 의도한 데이터가 쌓이는지 본다.

7. cleanup/compression cron
   - `03:00` cleanup과 일요일 `03:30` compression은 아직 운영 주기상 충분히 검증되지 않았다.
   - 로그/보고서 삭제 기준이 사용자에게 필요한 보관 기간과 맞는지 확인한다.

8. Perplexity/OpenAI 사용량
   - Perplexity는 충전형 API 사용량을 주기적으로 본다.
   - GPT-5.4 mini 호출량이 예상보다 커지는지 확인한다.
   - 비용 문제가 생기면 분석 후보 수, 보고서 생성 범위, Perplexity 호출 횟수를 먼저 점검한다.

9. KRX 로그인 안정성
   - 중복 로그인 modal 처리는 적용됐지만, KRX 사이트 UI 변경 가능성이 있다.
   - `HTML 응답 - 로그인 필요`, cookie 발급 실패, timeout이 반복되면 로그인 흐름부터 다시 본다.
   - logout cleanup timeout은 전체 배치를 막지 않도록 best-effort로 처리하지만, login iframe 접근 실패, 계정 인증 실패, cookie 발급 실패는 계속 원인 확인 대상이다.
   - session 검증 timeout은 KRX 지연일 수 있으므로 최근 검증 session은 보존한다. 실제 API 응답에서 `LOGOUT`이 오면 만료로 본다.

10. 실전투자 전환 전 안전 점검
    - 실전 key, 실계좌, 주문 가능 시간, 주문 종류, 매수/매도 금액, emergency stop 절차를 별도 checklist로 만든다.
    - 모의투자에서 최소 여러 차례 매수/매도/미체결/DB 정합성 검증이 끝나기 전에는 실전으로 전환하지 않는다.

## 운영 체크리스트

장 시작 전:

```bash
docker compose ps
docker compose exec -T prism-insight service cron status
docker compose exec -T prism-insight crontab -l
docker compose exec -T prism-insight bash -lc 'cd /app/prism-insight && set -a && . ./.env && set +a && python3 -c "from stock_tracking_agent import StockTrackingAgent; print(StockTrackingAgent._resolve_max_slots())"'
```

자동 실행 후:

```bash
tail -200 logs/kr_morning_$(date +%Y%m%d).log
tail -200 logs/kr_afternoon_$(date +%Y%m%d).log
```

확인할 내용:

- `Full pipeline complete` 여부
- Telegram 전송 성공 여부
- `Purchased`, `Sold` count
- `buyable quantity 0` 여부
- KIS portfolio count
- KIS open orders count
- DB `stock_holdings` count
- DB `trading_history` 기록

KIS와 DB는 항상 함께 확인한다. KIS 조회가 실패했는데 빈 포트폴리오처럼 보이는 상황을 특히 조심한다.

첫 매수 발생 후:

```bash
sqlite3 stock_tracking_db.sqlite 'SELECT ticker, company_name, buy_price, current_price, buy_date, account_key FROM stock_holdings;'
```

확인할 내용:

- KIS 앱 보유 종목/수량과 DB row 일치 여부
- Telegram 매수 메시지와 실제 체결 여부
- 미체결 주문 존재 여부
- 다음 오후/다음날 오전 실행에서 같은 종목을 중복 매수하지 않는지

## 다음 수정 시 주의사항

- 자동 매매 관련 수정은 반드시 작은 단위로 진행한다.
- 원본 prompt와 분석 순서는 가급적 유지한다.
- LLM-heavy report generation을 무리하게 병렬화하지 않는다.
- async 경로에 blocking network call을 새로 넣지 않는다.
- 매매 조건을 바꾸기 전에는 로그, DB, KIS 앱 상태를 함께 본다.
- 실전투자 전환 전에는 별도 문서/checklist를 만들고 사용자의 명시적 승인을 받는다.
- `.env` 로드 방식 변경 시 secret이 로그에 출력되지 않는지 확인한다.
- `docker/crontab.kd` 수정 후에는 현재 컨테이너에 `crontab /app/prism-insight/docker/crontab`으로 재설치하거나 컨테이너를 재생성한다.
- upstream에서 `docker-compose.yml`, `docker/entrypoint.sh`, `stock_tracking_agent.py`, `trading/domestic_stock_trading.py`, `cores/agents/trading_agents.py`가 바뀌면 이 문서의 로컬 가정과 충돌하지 않는지 확인한다.
- `main`에서 원본 sync 후 `kd-local`에 병합할 때는 위 파일들의 conflict 여부를 특히 본다.

## 테스트와 검증 제약

현재 로컬/컨테이너 환경에서 `pytest`가 설치되어 있지 않은 경우가 있었다. 테스트 명령이 실패하면 실패 이유를 명확히 남기고, 가능한 운영 검증으로 보완한다.

권장 테스트:

```bash
pytest tests/test_stock_tracking_max_slots.py
pytest tests/test_broker_tracking_consistency.py
pytest tests/test_multi_account_domestic.py
pytest tests/test_domestic_trading_time_windows.py
pytest tests/test_kis_credential_validation.py
pytest tests/test_patch_krx_data_client.py
```

`pytest`가 없을 때 최소 대체 검증:

```bash
git diff --check
docker compose exec -T prism-insight bash -lc 'cd /app/prism-insight && set -a && . ./.env && set +a && python3 -c "from stock_tracking_agent import StockTrackingAgent; print(StockTrackingAgent._resolve_max_slots())"'
docker compose exec -T prism-insight service cron status
docker compose exec -T prism-insight crontab -l
```

단, 대체 검증은 단위 테스트를 완전히 대신하지 않는다. trading 관련 코드 수정 후에는 가능하면 `pytest` 환경을 준비해 targeted test를 실행한다.

## 자주 쓰는 명령

컨테이너 상태:

```bash
docker compose ps
docker compose logs --tail=120 prism-insight
```

cron 확인:

```bash
docker compose exec -T prism-insight service cron status
docker compose exec -T prism-insight crontab -l
```

슬롯 설정 확인:

```bash
docker compose exec -T prism-insight bash -lc 'cd /app/prism-insight && set -a && . ./.env && set +a && python3 -c "from stock_tracking_agent import StockTrackingAgent; print(StockTrackingAgent._resolve_max_slots())"'
```

DB count 확인:

```bash
sqlite3 stock_tracking_db.sqlite 'SELECT COUNT(*) FROM stock_holdings;'
sqlite3 stock_tracking_db.sqlite 'SELECT COUNT(*) FROM trading_history;'
```

tracked 변경 확인:

```bash
git status --short --branch
git diff --check
git diff --name-only
```

## 관련 로컬 커밋 요약

- `3593d14 기능: 안전한 로컬 Docker 실행 환경 추가`
- `1ffcc79 수정: KIS 앱 키 접두어를 불투명 값으로 처리`
- `f33ed83 수정: KRX 중복 로그인 확인 모달 처리`
- `c891692 기능: Perplexity 미설정 시 분석 대체 경로 추가`
- `203fc03 안전: 국내 주식 휴장일 주문 차단`
- `30c5a48 수정: 모의투자 미체결 조회와 취소 식별자 보완`
- `e4077c3 수정: Docker MCP 실행과 OAuth 도구 호출 호환성 보완`
- `d97513c 설정: 국내 주식 최대 보유 슬롯을 5개로 제한`
- `8401464 설정: 국내 모의투자 운용한도와 예비금 적용`
- `b2d104a 안전: KIS 주문과 추적 DB 정합성 검증 강화`
- `3e38855 운영: 국내 모의투자 유지보수 일정 복원`
- `fb30d9c 운영: 로컬 cron 실행 시 환경 설정 로드`

## 새 context 시작 시 권장 첫 절차

1. `AGENTS.md`와 이 문서를 읽는다.
2. `git status --short --branch`로 브랜치와 dirty 상태를 확인한다.
3. `.env`, `kis_devlp.yaml` 등 비밀 파일은 출력하지 말고 필요한 key 존재 여부만 확인한다.
4. Docker/cron 상태와 슬롯 해석값이 정상인지 확인한다.
5. 사용자가 요청한 작업이 운영 설정인지, 코드 수정인지, 실제 주문/계좌 확인인지 구분한다.
6. 실제 매매 관련 액션은 반드시 사용자에게 방향을 설명한 뒤 진행한다.
