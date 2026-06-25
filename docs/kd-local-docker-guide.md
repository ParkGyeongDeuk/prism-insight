# kd-local Docker 운영 가이드

이 문서는 사용자가 직접 PRISM-INSIGHT 로컬 모의투자 컨테이너를 켜고, 멈추고, 상태와 로그를 확인할 수 있도록 정리한 실무용 명령 모음이다.

기준 환경:

- 작업 위치: `/Users/kd/Desktop/project/etc/prism-insight`
- compose 서비스명: `prism-insight`
- 컨테이너명: `prism-insight-container`
- 로컬 운영 compose 구성: `docker-compose.yml` + `docker-compose.local.yml`
- 국내 자동 스케줄: `docker/crontab.kd`

## 1. 시작 전에 확인할 것

터미널을 열고 프로젝트 루트로 이동한다.

```bash
cd /Users/kd/Desktop/project/etc/prism-insight
```

`.env`에 다음 값이 있어야 로컬 운영 설정이 적용된다.

```env
COMPOSE_FILE=docker-compose.yml:docker-compose.local.yml
PRISM_ENABLE_CRON=true
PRISM_OPENAI_AUTH_MODE=chatgpt_oauth
PRISM_KR_MAX_SLOTS=5
PRISM_KR_TOTAL_BUDGET=2000000
PRISM_KR_CASH_RESERVE=400000
```

중요:

- `.env`, `mcp_agent.secrets.yaml`, `trading/config/kis_devlp.yaml`에는 비밀값이 들어 있으므로 화면 공유, 커밋, 문서 복사 시 주의한다.
- 운영 중에는 `docker compose down -v`를 사용하지 않는다. `-v`는 Docker volume을 삭제할 수 있다.
- 실제 모의투자 판단과 주문 경로가 포함된 명령은 장중에 중복 실행하지 않도록 조심한다.

## 2. 빌드와 실행

처음 실행하거나 소스 변경 후 이미지를 새로 만들 때:

```bash
docker compose build prism-insight
docker compose up -d --force-recreate prism-insight
```

이미 빌드된 이미지로 컨테이너만 켤 때:

```bash
docker compose up -d prism-insight
```

컨테이너가 정상인지 확인한다.

```bash
docker compose ps
```

정상이라면 `prism-insight` 서비스가 `running` 또는 `healthy` 상태로 보인다.

## 3. 중지와 재시작

잠깐 멈출 때:

```bash
docker compose stop prism-insight
```

다시 시작할 때:

```bash
docker compose start prism-insight
```

재시작만 할 때:

```bash
docker compose restart prism-insight
```

컨테이너를 내렸다가 다시 만들 때:

```bash
docker compose down
docker compose up -d prism-insight
```

주의:

- `docker compose down`은 컨테이너와 네트워크를 내리지만, 기본적으로 named volume은 지우지 않는다.
- `docker compose down -v`는 volume까지 삭제할 수 있으므로 로컬 운영에서는 사용하지 않는다.

## 4. 상태 확인

컨테이너 상태:

```bash
docker compose ps
```

컨테이너 시작 로그:

```bash
docker compose logs --tail=120 prism-insight
```

실시간 컨테이너 로그:

```bash
docker compose logs -f prism-insight
```

cron 서비스 상태:

```bash
docker compose exec prism-insight service cron status
```

현재 설치된 cron 스케줄:

```bash
docker compose exec prism-insight crontab -l
```

로컬 슬롯 설정이 컨테이너에서 `5`로 해석되는지 확인:

```bash
docker compose exec prism-insight bash -lc 'cd /app/prism-insight && set -a && . ./.env && set +a && python3 -c "from stock_tracking_agent import StockTrackingAgent; print(StockTrackingAgent._resolve_max_slots())"'
```

결과가 `5`이면 `PRISM_KR_MAX_SLOTS=5`가 정상 적용된 것이다.

## 5. 컨테이너 안으로 들어가기

일반 shell 접속:

```bash
docker compose exec prism-insight bash
```

컨테이너 안에서 자주 확인하는 위치:

```bash
pwd
ls -la
ls -la logs
ls -la reports
ls -la pdf_reports
```

컨테이너에서 빠져나올 때:

```bash
exit
```

참고:

- 프로젝트 루트 전체가 bind mount되는 구조는 아니다. 소스 코드는 이미지 안에 복사되어 있고, 일부 운영 파일과 산출물만 호스트와 연결된다.
- `.env`, `mcp_agent.config.yaml`, `mcp_agent.secrets.yaml`, `trading/config/kis_devlp.yaml`, `logs`, `reports`, `pdf_reports`, `html_reports`, `charts`, `telegram_messages`, `stock_tracking_db.sqlite`는 호스트에서도 바로 확인할 수 있다.
- 소스 코드나 문서 변경을 컨테이너 안에도 반영하려면 보통 이미지를 다시 빌드하고 컨테이너를 재생성한다.

## 6. 로그 확인

오전 분석 로그:

```bash
tail -200 logs/kr_morning_$(date +%Y%m%d).log
```

오후 분석 로그:

```bash
tail -200 logs/kr_afternoon_$(date +%Y%m%d).log
```

성과 추적 로그:

```bash
tail -200 logs/performance_$(date +%Y%m%d).log
```

Loop SHADOW 관측 로그:

```bash
tail -200 logs/loop_a_shadow_$(date +%Y%m%d).log
tail -200 logs/loop_b_shadow_$(date +%Y%m%d).log
tail -200 logs/loop_c_shadow_$(date +%Y%m%d).log
```

실시간으로 따라볼 때:

```bash
tail -f logs/kr_morning_$(date +%Y%m%d).log
```

로그에서 우선 확인할 문구:

- `Full pipeline complete`
- `Stock tracking system batch completed successfully`
- `Telegram`
- `Purchased`
- `Sold`
- `Skipping trading`
- `token_invalidated`
- `Analysis failed`
- `KIS`
- `portfolio`
- `open orders`

## 7. 자동 스케줄 확인

로컬 cron 파일은 `docker/crontab.kd`이고, 컨테이너 안에서는 `/app/prism-insight/docker/crontab`으로 mount된다.

현재 주요 스케줄:

- 평일 `07:00`: 국내 종목 코드/이름 갱신
- 평일 `09:30`: 국내 오전 분석 및 모의투자 판단
- 평일 `15:40`: 국내 오후 분석 및 모의투자 판단
- 평일 `17:00`: 성과 추적 batch
- 장중: Loop A/B/C SHADOW 관측
- 매일 `03:00`: 로그/보고서 정리
- 일요일 `03:30`: trading memory 압축

`docker/crontab.kd`를 수정한 뒤에는 다음 중 하나가 필요하다.

컨테이너에 crontab만 다시 설치:

```bash
docker compose exec prism-insight crontab /app/prism-insight/docker/crontab
docker compose exec prism-insight crontab -l
```

또는 컨테이너 재생성:

```bash
docker compose up -d --force-recreate prism-insight
```

## 8. 수동 실행

종목 코드/이름 갱신:

```bash
docker compose exec prism-insight python3 update_stock_data.py
```

성과 추적 dry-run:

```bash
docker compose exec prism-insight python3 performance_tracker_batch.py --dry-run
```

성과 추적 상태 리포트:

```bash
docker compose exec prism-insight python3 performance_tracker_batch.py --report
```

오전 분석 수동 실행:

```bash
docker compose exec prism-insight python3 stock_analysis_orchestrator.py --mode morning
```

오후 분석 수동 실행:

```bash
docker compose exec prism-insight python3 stock_analysis_orchestrator.py --mode afternoon
```

주의:

- `stock_analysis_orchestrator.py --mode morning/afternoon`은 보고서 생성, Telegram 전송, tracking batch, KIS 모의투자 주문 경로를 포함한다.
- 자동 cron 실행 시간과 겹치지 않게 실행한다.
- Telegram 전송 없이 분석을 확인하려면 `--no-telegram`을 붙일 수 있지만, tracking/모의투자 판단 경로까지 완전히 비활성화하는 옵션은 아니다.

## 9. 테스트 실행

테스트 의존성은 운영 이미지 기본 의존성과 분리되어 있다.

처음 한 번 또는 컨테이너 재생성 후 필요할 때:

```bash
docker compose exec prism-insight pip install -r requirements-dev.txt
```

예시 테스트:

```bash
docker compose exec prism-insight python3 -m pytest tests/test_stock_tracking_agent_process_reports.py
docker compose exec prism-insight python3 -m pytest tests/test_report_reader.py
docker compose exec prism-insight python3 -m pytest tests/test_broker_tracking_consistency.py
```

여러 테스트를 한 번에 실행:

```bash
docker compose exec prism-insight python3 -m pytest tests/test_stock_tracking_agent_process_reports.py tests/test_report_reader.py
```

테스트가 너무 오래 걸리거나 외부 API를 부를 위험이 있어 보이면 중단하고, 대상 테스트를 더 좁혀 실행한다.

## 10. DB 확인

현재 보유 DB:

```bash
sqlite3 stock_tracking_db.sqlite 'SELECT ticker, company_name, buy_price, current_price, buy_date, account_key FROM stock_holdings;'
```

매도 이력:

```bash
sqlite3 stock_tracking_db.sqlite 'SELECT ticker, company_name, buy_price, sell_price, profit_rate, sell_date FROM trading_history ORDER BY sell_date DESC LIMIT 20;'
```

watchlist 최근 기록:

```bash
sqlite3 stock_tracking_db.sqlite 'SELECT id, ticker, company_name, decision, buy_score, analyzed_date FROM watchlist_history ORDER BY id DESC LIMIT 20;'
```

컨테이너 안에서 실행하고 싶을 때:

```bash
docker compose exec prism-insight sqlite3 /app/prism-insight/stock_tracking_db.sqlite 'SELECT ticker, company_name, buy_price, current_price FROM stock_holdings;'
```

주의:

- DB는 실제 모의투자 상태를 추적하는 운영 데이터다.
- `UPDATE`, `DELETE`, `INSERT`는 원인과 기대 결과를 확인한 뒤에만 실행한다.
- KIS 앱/계좌 조회 결과와 DB가 다르면 DB만 보고 판단하지 않는다.

## 11. 소스 변경 후 컨테이너 반영

현재 compose는 프로젝트 루트 전체를 컨테이너에 bind mount하지 않는다. Python 소스, 문서, Dockerfile에 포함되어 이미지로 복사되는 파일을 바꿨다면 컨테이너에 반영하기 위해 재빌드와 재생성이 필요하다.

반대로 `.env`, secret/config 파일, `logs`, `reports`, `pdf_reports`, `telegram_messages`, `stock_tracking_db.sqlite`, `docker/crontab.kd`처럼 compose에서 직접 mount하는 파일은 호스트 변경이 컨테이너에서도 보인다. 단, crontab은 파일이 보여도 cron daemon에 다시 설치해야 적용된다.

권장 절차:

```bash
git status --short --branch
docker compose build prism-insight
docker compose up -d --force-recreate prism-insight
docker compose ps
docker compose exec prism-insight service cron status
docker compose exec prism-insight crontab -l
```

재생성 후 dev 테스트가 필요하면:

```bash
docker compose exec prism-insight pip install -r requirements-dev.txt
```

## 12. 문제 상황별 빠른 확인

오전/오후 Telegram이 오지 않았을 때:

```bash
docker compose ps
docker compose exec prism-insight service cron status
docker compose exec prism-insight crontab -l
tail -200 logs/kr_morning_$(date +%Y%m%d).log
tail -200 logs/kr_afternoon_$(date +%Y%m%d).log
```

KRX 로그인 문제가 의심될 때:

```bash
tail -200 logs/kr_morning_$(date +%Y%m%d).log
tail -200 logs/kr_afternoon_$(date +%Y%m%d).log
```

로그에서 `login`, `KRX`, `session`, `timeout`, `HTML 응답 - 로그인 필요` 문구를 확인한다.

ChatGPT OAuth 문제가 의심될 때:

```bash
docker compose logs --tail=120 prism-insight
tail -200 logs/kr_morning_$(date +%Y%m%d).log
tail -200 logs/kr_afternoon_$(date +%Y%m%d).log
```

로그에서 `token_invalidated`, `401`, `quota`, `ChatGPT OAuth proxy` 문구를 확인한다.

보유 수량이나 매도 메시지가 이상할 때:

```bash
sqlite3 stock_tracking_db.sqlite 'SELECT ticker, company_name, buy_price, current_price, buy_date, account_key FROM stock_holdings;'
sqlite3 stock_tracking_db.sqlite 'SELECT ticker, company_name, buy_price, sell_price, profit_rate, sell_date FROM trading_history ORDER BY sell_date DESC LIMIT 20;'
tail -200 logs/kr_afternoon_$(date +%Y%m%d).log
```

이 경우 KIS 앱의 실제 보유/미체결 주문도 함께 확인한다.

## 13. 평소 확인 루틴

장 시작 전:

```bash
docker compose ps
docker compose exec prism-insight service cron status
docker compose exec prism-insight crontab -l
docker compose exec prism-insight bash -lc 'cd /app/prism-insight && set -a && . ./.env && set +a && python3 -c "from stock_tracking_agent import StockTrackingAgent; print(StockTrackingAgent._resolve_max_slots())"'
```

오전 분석 후:

```bash
tail -200 logs/kr_morning_$(date +%Y%m%d).log
sqlite3 stock_tracking_db.sqlite 'SELECT ticker, company_name, buy_price, current_price FROM stock_holdings;'
```

오후 분석 후:

```bash
tail -200 logs/kr_afternoon_$(date +%Y%m%d).log
sqlite3 stock_tracking_db.sqlite 'SELECT ticker, company_name, buy_price, current_price FROM stock_holdings;'
```

장 마감 후:

```bash
tail -200 logs/performance_$(date +%Y%m%d).log
tail -100 logs/loop_a_shadow_$(date +%Y%m%d).log
tail -100 logs/loop_b_shadow_$(date +%Y%m%d).log
tail -100 logs/loop_c_shadow_$(date +%Y%m%d).log
```

정상 운영의 기준:

- 컨테이너가 running/healthy 상태다.
- cron이 실행 중이다.
- crontab이 `docker/crontab.kd` 기준으로 설치되어 있다.
- 슬롯 설정 확인 결과가 `5`다.
- 오전/오후 로그에 `Full pipeline complete`가 있다.
- KIS 실제 보유/미체결 상태와 `stock_tracking_db.sqlite`가 일치한다.
