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

`.env`에는 다음 값이 필요하다.

```env
COMPOSE_FILE=docker-compose.yml:docker-compose.local.yml
PRISM_ENABLE_CRON=true
PRISM_OPENAI_AUTH_MODE=chatgpt_oauth
PRISM_OAUTH_CALLBACK_HOST=0.0.0.0
PRISM_KR_MAX_SLOTS=5
PRISM_KR_TOTAL_BUDGET=2000000
PRISM_KR_CASH_RESERVE=400000
```

`docker-compose.local.yml`의 역할:

- 국내 로컬 운영용 환경변수를 컨테이너에 전달한다.
- `trading/config/kis_devlp.yaml`을 컨테이너에 bind mount한다.
- ChatGPT OAuth token을 Docker volume `prism-auth`에 보존한다.
- `docker/crontab.kd`를 컨테이너의 `/app/prism-insight/docker/crontab`으로 mount한다.
- OAuth callback port `1455`를 `127.0.0.1`에만 노출한다.

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
