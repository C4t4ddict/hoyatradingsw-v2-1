# HoyaTradingSW v2

Binance API + TradingView Webhook + Python 기반 자동매매/백테스트 플랫폼.

- 백테스트 시세는 ccxt를 통한 거래소 공개 OHLCV API(무료) 사용

> 현재 Spot / Futures(USDT-M) **둘 다 지원**

요구한 핵심 규칙을 기준으로 구현을 진행했고, 앞으로 기능 추가 시 이 README를 계속 업데이트합니다.

> v2 핵심: 기존 자동매매/백테스트 기능을 유지하면서, 신뢰 가능한 뉴스/공식 발표를 점수화해 진입을 보수적으로 필터링합니다.

---

## 프로그램 개요

HoyaTradingSW는 아래 3가지를 하나로 묶은 실행형 트레이딩 도구입니다.

1. **백테스트 엔진**: 기간 설정 가능한 전략 검증
2. **실행 엔진**: TradingView 알림(Webhook) → Binance 주문 연결
3. **현대적 UI 대시보드**: 성과(수익률) 중심 모니터링

---

## 현재 구현 기능

### 1) 백테스팅 (기간 설정 가능)
- 백테스트 시작일/종료일 직접 선택
- Binance 상장 심볼(spot/futures, USDT 마켓만) 자동 연동 + 검색 가능한 드롭다운
- 최소 24h 거래대금(USDT) 필터로 저유동성 심볼 제외 가능
- 타임프레임(5m/15m/1h) 선택
- 포지션 방향 선택: futures는 long/short/both, spot은 long-only
- 파라미터 변경 시 자동 백테스트 옵션 + OHLCV/펀딩 데이터 캐시로 속도 최적화
- 실시간 모의투자(가상자금) 모드: 시작 시점부터 현재 시세 기준으로 지속 갱신
- 전략 선택 가능:
  - `[NEW] trend_continuation_system` (고확률 추세 추종)
  - `[NEW] liquidation_reversal_setup` (청산 사냥 역추세)
  - `[PRO] ensemble_regime` (레짐 기반 혼합 운용, 가중치/레짐 임계값 튜닝 가능)
  - `[ADD] dual_momentum_trend`
  - `[ADD] volatility_breakout_atr`
  - `[ADD] donchian_vol_filter`
  - `[ADD] mean_reversion_zscore`
  - `[ADD] rsi_failure_structure`
  - `[ADD] vwap_anchored_intraday`
  - `[ADD] funding_oi_reversal_pro`
  - `[ADD] adaptive_vol_target`
  - `[TOP] tlab_strategy_ever_need` (The Only Trading Strategy You'll Ever Need)
  - `[TOP] tlab_fvg_secret` (I Found A Secret To Fair Value Gaps)
  - `[TOP] tlab_candlestick_filter` (Candlestick Patterns Don't Work ...)
  - `[TOP] tlab_daytrading_beginner` (How To Day Trade As A Complete Beginner)
  - `ema_cross` (추세추종)
  - `rsi_reversion` (과매도 반등)
  - `breakout_20` (20봉 고가 돌파)
- 전략 선택을 상승장/횡보장/하락장 3개 전략군 드롭다운으로 분리
- 메인 뉴스 패널: 2x2 카드, 자세히 보기 확장, 페이지 네비게이션(< / >), 새로고침
- 뉴스 한글 번역 제목/요약 + 영향도(상승 가능성/하락 가능성/중립) + 중요도 점수 표시, 저품질 제목 필터
- 뉴스 번역 결과 로컬 캐시(파일) 저장으로 새로고침 시 빠른 로딩
- 파라미터 튜닝 가능:
  - EMA fast/slow
  - RSI period/lower/upper
  - breakout lookback
  - (선물) Funding Rate(%/8h)
  - (선물) Leverage(백테스트 전용)
  - Binance 실제 펀딩비 이력 사용(무료 funding history API)
- 전략 3종 비교 버튼으로 수익률/승률/트레이드 수 비교 가능
- 전략 포트폴리오(가중치 입력형) 수익률/PF/MDD 비교 제공
- 파라미터 최적화(grid search) 버튼 제공 (성향 설명 포함: return/balanced/safe/aggressive)
- Ensemble 전용 최적화(가중치/레짐 임계값 + MDD/청산/거래수 제약) 제공
- 저장된 `ensemble_top_*` 프리셋 일괄 비교 기능 제공
- 워크포워드 테스트(train/test 분리) 버튼 제공
- 파라미터 저장/불러오기(심볼+타임프레임+전략별)
- 파라미터 프리셋 이름 저장/선택 지원 (전략 선택 시 드롭다운)
- 저장 파라미터의 SL%/TP RR을 webhook 실전 엔진에 자동 반영
- webhook 진입 전 기대수익률/허용MDD 임계값 필터 지원
- webhook에서 조건 통과 버전 자동선택(`WEBHOOK_AUTO_SELECT_VERSION=true`) 지원
- UTC 거래 시간 윈도우 제한(`TRADING_WINDOW_UTC`) 지원
- 변동성 급등 시 자동 진입중지(VOL_PAUSE) 지원
- 성과 지표 확장: Profit Factor, Max Drawdown
- 월별 백테스트 리포트(월별 PnL/승률/거래수/PF/MDD) 제공
- 전략 파라미터 버전 저장/활성화 + 포트폴리오 가중치 저장 지원
- 월별 리포트 CSV 다운로드 지원
- 결과 제공:
  - 수익률(%) **(선택 기간 기준 총 수익률)**
  - 종료 자본(USDT)
  - 총 트레이드 수
  - 승률(%)
  - 강제청산 횟수(레버리지/유지증거금 모델)
  - Equity Curve
  - 캔들 차트 + 매수/매도 시점 마커

### 2) 현대적 UI 실행 환경
- `streamlit` + `plotly` 기반 대시보드 제공
- 단일 명령으로 실행 가능:
  ```bash
  streamlit run dashboard.py
  ```
- 상단 핵심 KPI 카드 + 차트 중심 구조

### 3) 공격적 투자 / 안전 투자 모드
- `safe`, `aggressive` 프로필 제공
- 프로필별 자동 반영 항목:
  - 거래당 리스크(risk_per_trade)
  - 포지션 상한(max_position)
  - 기본 손절폭(default_stop_loss_pct)
  - 목표 RR(target_rr)

### 4) 투자 시작 후 현재까지 수익률 표시(가시성 최우선)
- 대시보드 최상단 KPI에 **누적 수익률(시작~현재)** 표시
- 거래 이벤트 로그 기반 성과 집계
- 잔고 변화 라인 차트 제공

### 5) 실전 운용용 핵심 기능(강화 버전)
- TradingView Webhook 수신 서버 (`/webhook`)
- 계정 상태 조회 API (`/account/status`)
- 트레이드 결과 반영 API (`/trade/result`)로 손익 누적
- 전략 ON/OFF 토글 (config)
- 허용 심볼 화이트리스트(현물/선물 분리)
- 동시 포지션 제한(현물/선물 마켓별 + 심볼별)
- `side` 값 엄격 검증(`buy`/`sell`)
- Webhook 토큰 인증 (`X-Webhook-Token`)
- `signal_id` 기반 중복 신호 방지(파일 영속 저장 + TTL)
- 선물 레버리지/마진모드/포지션모드 설정 API
- DRY_RUN 모드 기본값 유지
- Binance testnet 옵션 제공

### 6) 고급 리스크 가드레일 + 자동 알림
- 일일 손실 한도 초과 시 신규 진입 자동 중지
- 연속 손실 횟수 초과 시 신규 진입 자동 중지
- **현물/선물 각각 별도 한도 적용 가능**
- 주문 실패/가드 발동 시 Telegram 알림(옵션)

### 7) 실현/미실현 손익 분리 표시
- 거래소 데이터 기반 PnL snapshot 계산
  - 실현손익: 체결 이력의 realized 필드 합산(지원 거래소)
  - 미실현손익: 활성 포지션의 unrealizedPnl 합산
- 대시보드 상단 KPI + 실시간 계정 탭에 동시 노출

---

## 디렉토리 구조

- `dashboard.py` : Streamlit UI (실행 대시보드)
- `webhook_server.py` : FastAPI Webhook 서버
- `backtest.py` : 기간형 백테스트 로직
- `exchange.py` : ccxt 거래소 연동 (Binance)
- `risk.py` : 포지션 사이징/TP 계산
- `profiles.py` : 투자 성향 프로필(safe/aggressive)
- `performance.py` : 거래 로그/수익률 집계
- `risk_guard.py` : 일일 손실/연속 손실 가드레일 상태 관리
- `notifier.py` : Telegram 경보 전송
- `idempotency.py` : 웹훅 중복 방지 저장소(영속 + TTL)
- `strategy_store.py` : 전략 파라미터 저장/불러오기
- `wallet_history.py` : 실지갑 스냅샷 저장/조회
- `pinescript/strategy_template.pine` : TradingView 전략 템플릿
- `config.example.yaml` : 전략/심볼 설정
- `.env.example` : API/운용 환경 변수

---

## 실행 방법

> 권장 Python 버전: **3.10+**

```bash
cd HoyaTradingSW
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 1) Webhook 서버 실행
```bash
python main.py
```

헬스체크:
```bash
curl http://127.0.0.1:8000/health
```

### 2) UI 대시보드 실행
```bash
streamlit run dashboard.py
```

### 3) 실시간 계정 상태 API 테스트
```bash
curl -H "X-Webhook-Token: CHANGE_ME" "http://127.0.0.1:8000/account/status?market_type=spot"
curl -H "X-Webhook-Token: CHANGE_ME" "http://127.0.0.1:8000/account/status?market_type=futures"
```

### 4) 트레이드 결과 반영(리스크 가드 업데이트)
```bash
curl -X POST http://127.0.0.1:8000/trade/result \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: CHANGE_ME" \
  -d '{"strategy":"ema_cross","symbol":"BTC/USDT","realized_pnl":-12.5}'
```

### 5) 일일 리포트 알림 발송(옵션)
```bash
curl -X POST http://127.0.0.1:8000/report/daily \
  -H "X-Webhook-Token: CHANGE_ME"
```

### 6) 선물 레버리지/격리마진 설정 API
```bash
curl -X POST http://127.0.0.1:8000/futures/configure \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: CHANGE_ME" \
  -d '{"symbol":"BTC/USDT:USDT","leverage":5,"margin_mode":"isolated"}'
```

### 7) 선물 포지션 모드(one-way / hedge) 설정 API
```bash
curl -X POST http://127.0.0.1:8000/futures/position-mode \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: CHANGE_ME" \
  -d '{"hedged":true}'
```

### 8) 전략 파라미터 조회/버전 활성화 API
```bash
curl -H "X-Webhook-Token: CHANGE_ME" "http://127.0.0.1:8000/strategy/params?symbol=BTC/USDT&timeframe=5m&strategy=ema_cross"

curl -H "X-Webhook-Token: CHANGE_ME" "http://127.0.0.1:8000/strategy/versions/compare?symbol=BTC/USDT&timeframe=5m&strategy=ema_cross&limit=10"

curl -X POST http://127.0.0.1:8000/strategy/activate-version \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: CHANGE_ME" \
  -d '{"symbol":"BTC/USDT","timeframe":"5m","strategy":"ema_cross","version_index":2}'
```

### 9) 포트폴리오 가중치 저장/조회 API
```bash
curl -X POST http://127.0.0.1:8000/portfolio/weights \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: CHANGE_ME" \
  -d '{"symbol":"BTC/USDT","timeframe":"5m","ema":40,"rsi":30,"breakout":30}'

curl -H "X-Webhook-Token: CHANGE_ME" "http://127.0.0.1:8000/portfolio/weights?symbol=BTC/USDT&timeframe=5m"
```

### 10) 전략 태그/락 API (stable, test 운용)
```bash
curl -X POST http://127.0.0.1:8000/strategy/tag \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: CHANGE_ME" \
  -d '{"symbol":"BTC/USDT","timeframe":"5m","strategy":"ema_cross","tag":"stable","version_index":2}'

curl -X POST http://127.0.0.1:8000/strategy/promote \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: CHANGE_ME" \
  -d '{"symbol":"BTC/USDT","timeframe":"5m","strategy":"ema_cross","from_tag":"test","to_tag":"stable"}'

curl -H "X-Webhook-Token: CHANGE_ME" "http://127.0.0.1:8000/strategy/tag?symbol=BTC/USDT&timeframe=5m&strategy=ema_cross&tag=stable"

curl -X POST http://127.0.0.1:8000/strategy/lock \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: CHANGE_ME" \
  -d '{"symbol":"BTC/USDT","timeframe":"5m","strategy":"ema_cross","locked":true,"reason":"검증 중"}'

curl -H "X-Webhook-Token: CHANGE_ME" "http://127.0.0.1:8000/strategy/lock?symbol=BTC/USDT&timeframe=5m&strategy=ema_cross"
```

---

## Binance 연동 설정

`.env` 예시:

```env
EXCHANGE=binance
API_KEY=YOUR_BINANCE_API_KEY
API_SECRET=YOUR_BINANCE_API_SECRET
BINANCE_DEFAULT_TYPE=spot
BINANCE_TESTNET=true
DRY_RUN=true
WEBHOOK_TOKEN=CHANGE_ME
PERF_LOG=data/performance_log.jsonl
DAILY_LOSS_LIMIT_USDT=30
MAX_CONSECUTIVE_LOSSES=3
DAILY_LOSS_LIMIT_USDT_SPOT=30
MAX_CONSECUTIVE_LOSSES_SPOT=3
DAILY_LOSS_LIMIT_USDT_FUTURES=30
MAX_CONSECUTIVE_LOSSES_FUTURES=3
RISK_STATE_PATH=data/risk_state.json
RISK_STATE_PATH_SPOT=data/risk_state_spot.json
RISK_STATE_PATH_FUTURES=data/risk_state_futures.json
MAX_CONCURRENT_POSITIONS_SPOT=5
MAX_CONCURRENT_POSITIONS_FUTURES=3
ALERT_TELEGRAM_BOT_TOKEN=
ALERT_TELEGRAM_CHAT_ID=
IDEMPOTENCY_STORE_PATH=data/idempotency_store.json
IDEMPOTENCY_TTL_HOURS=48
STRATEGY_STORE_PATH=data/strategy_params.json
WEBHOOK_MIN_EXPECTED_RETURN_PCT=-999
WEBHOOK_MAX_ALLOWED_MDD_PCT=999
WEBHOOK_AUTO_SELECT_VERSION=false
WEBHOOK_LIVE_ALLOWED_TAGS=stable
WEBHOOK_TEST_TAG_FORCE_DRY_RUN=true
TRADING_WINDOW_UTC=00:00-23:59
VOL_PAUSE_ENABLED=false
VOL_LOOKBACK_CANDLES=12
VOL_SPIKE_THRESHOLD_PCT=3.0
```

### 권장 순서
1. `BINANCE_TESTNET=true` + `DRY_RUN=true`로 검증
2. 웹훅/백테스트/로그 정상 확인
3. 소액 실거래로 단계 전환

---

## TradingView Webhook 연결

1. 로컬 서버를 외부 HTTPS로 노출(ngrok/cloudflared)
2. TradingView Alert의 Webhook URL에 `/webhook` 입력
3. Alert 메시지(JSON) 예시:

```json
{
  "strategy": "ema_cross",
  "symbol": "BTC/USDT",
  "side": "buy",
  "price": {{close}},
  "risk_profile": "safe",
  "market_type": "spot",
  "timeframe": "5m",
  "strategy_version": 3,
  "strategy_tag": "stable"
}
```

4. 헤더에 토큰 추가:
   - `X-Webhook-Token: <WEBHOOK_TOKEN>`
5. 선물 신호는 `market_type: "futures"` + 선물 심볼 형식 사용
   - 예: `BTC/USDT:USDT`

---

## 운영 안전 수칙

- 기본값은 `DRY_RUN=true`
- API 키는 **출금 권한 금지**
- 실거래 전 최소 1~2일 페이퍼 검증
- 전략 변경 후 반드시 재백테스트

---

## 다음 개발 예정 (우선순위)

1. 체결 데이터 기반 실현/미실현 손익 정확 집계(현재는 기본 필드 구조만 반영)
2. Max Drawdown, Profit Factor, Sharpe 추적
3. 웹훅 중복방지 영속화(파일/Redis) + 재시도 큐
4. 주문 실패 자동 알림(Telegram/Discord)
5. 포트폴리오 모드(다중 심볼 자본 배분)
6. 전략 파라미터 최적화(기간별 walk-forward)
7. 거래 비용/슬리피지 모델 고도화

---

## 면책

이 소프트웨어는 투자 보조 도구이며, 최종 투자 책임은 사용자에게 있습니다.

---

## v2 추가 기능: 시장 인텔리전스 기반 투자

- 새 모듈: `market_intel.py`
  - Reuters / CoinDesk / The Block / Fed / SEC / Treasury RSS 수집
  - BTC 연관 키워드 + 호재/악재 키워드 점수화
  - 소스 신뢰도 가중치 반영
  - 캐시(`data/market_intel_cache.json`)로 과도한 요청 방지
- 대시보드 새 탭: **시장 인텔리전스**
  - 종합 점수 / 바이어스(bullish/neutral/bearish) / 신뢰도 / 분석 건수
  - 상위 이슈 카드/테이블 확인
- Webhook 진입 필터 강화
  - `MARKET_INTEL_FILTER_ENABLED=true`면 진입 전 시장 점수 검사
  - 점수가 임계값보다 낮거나 bearish일 때 buy 진입 보류 가능

### 실행
```bash
cd HoyaTradingSW_v2
pip install -r requirements.txt
uvicorn webhook_server:app --reload --port 8000
streamlit run dashboard.py
```

### v2 추가 설정 (포지션 사이징 가감)
- `MARKET_INTEL_SIZE_UP_BULLISH` : bullish buy 시 포지션 배수 (기본 1.15)
- `MARKET_INTEL_SIZE_DOWN_BEARISH` : bearish 구간 포지션 축소 배수 (기본 0.65)
- `MARKET_INTEL_TWEET_RSS` : 공식 계정 RSS 브릿지 추가
  - 형식: `name|url|trust;name2|url2|trust2`

### 자동 수집/추적 (v2)
- 시장 인텔리전스는 백그라운드 워커가 `MARKET_INTEL_AUTO_REFRESH_SEC` 주기로 자동 갱신
- 기본적으로 Google News 검색 RSS를 자동 수집:
  - `trump bitcoin`, `trump crypto policy`, `bitcoin fed rate decision`
  - `bitcoin war oil sanctions`, `bitcoin middle east conflict`, `bitcoin geopolitical risk` 등
- 트럼프 관련 이슈/예정 발표(FOMC/CPI/연설 등) 키워드를 별도 집계
- 수동 수집 없이도 예정된 발표/돌발 기사 흐름이 자동 반영됨
- 가격 급변 시점(BTC 1h 변동률 기준) 역추적 백필 스크립트로 당시 관련 뉴스도 추가 수집 가능

### 국제정세 / 거시경제 통합 (v2 확장)
- 시장 인텔리전스를 3개 축으로 분리 집계:
  - `crypto_score` : 비트코인/ETF/거래소/규제 직접 이슈
  - `macro_score` : 금리/FOMC/CPI/고용/달러/채권금리
  - `geo_score` : 전쟁/관세/제재/미중갈등/선거/트럼프 등 국제정세
- 대시보드에서 최종 시그널을 `공격 / 중립 / 방어`로 표시
- 국제정세 리스크가 높으면 최종 시그널을 방어로 낮춤

## 무료 ML 예측 파이프라인 (v2)
- `ml_dataset.py`
  - 수집 이벤트 저장(`data/ml_events.jsonl`)
  - BTC 가격 반응 라벨링(`1h/4h/24h`)
  - 학습 CSV 생성(`data/ml_dataset.csv`)
- `train_model.py`
  - TF-IDF + RandomForest 기반 무료 로컬 학습
- `predict_model.py`
  - 저장된 모델로 개별 이벤트 상승 확률 예측

### 학습 실행
```bash
cd HoyaTradingSW_v2
pip install -r requirements.txt
python train_model.py
```

### 대시보드 ML 예측 카드
- 최신 이벤트 기준으로 `1h / 4h / 24h 상승확률` 표시
- 모델이 아직 없거나 학습 데이터가 부족하면 0%로 표시될 수 있음

### ML 진입 필터 (v2)
- `ML_FILTER_ENABLED=true`면 최신 이벤트의 ML 예측 확률을 함께 사용
- 기본 기준:
  - `ML_MIN_UP_PROBA_4H=0.52`
  - 4시간 상승확률이 기준보다 낮으면 buy 진입 보류
- 포지션 크기 추가 조정:
  - 4h 상승확률 >= 65% → 소폭 확대
  - 4h 상승확률 < 52% → 축소

### 혼합 ML 점수 (v2)
- `1h / 4h / 24h` 상승확률을 가중 평균해서 최종 ML 점수 계산
- 기본 가중치:
  - `ML_WEIGHT_1H=0.2`
  - `ML_WEIGHT_4H=0.5`
  - `ML_WEIGHT_24H=0.3`
- `ML_MIN_COMPOSITE_SCORE=0.54` 미만이면 buy 진입을 보수적으로 차단
