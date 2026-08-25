# HoyaTradingSW v2.1

- 목표: Streamlit UI에서 FastAPI + Next.js UI 구조로 이관
- 방향: 토스 스타일 UX, 모의투자/시장 인텔/실시간 계정 중심
- 기존 엔진: 유지
- UI: `frontend/` Next.js
- API: `backend/` FastAPI

## 실행

### 요구 환경

- Python 3.12 권장
- Node.js 20.9.0 이상
- 실계좌 키 없이 확인할 때 `.env.example`의 `DRY_RUN=true`, `BINANCE_TESTNET=true` 유지

### backend
PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item -LiteralPath .env.example -Destination .env
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8010
```

Windows CMD:

```bat
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
copy .env.example .env
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8010
```

macOS/Linux 또는 Git Bash:

```bash
python -m venv .venv
source .venv/bin/activate  # Git Bash on Windows: source .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8010
```

### frontend
```bash
cd frontend
npm ci
npm run dev
```

- 프론트엔드: http://127.0.0.1:3001
- 백엔드 상태: http://127.0.0.1:8010/healthz
- Windows 일괄 실행: `restart_and_run.bat`

## 현재 주요 API
### 공통
- `GET /healthz`
  - backend 생존 확인

### overview
- `GET /api/overview`
  - summary
  - market_brief
  - ml_signal

### intel
- `GET /api/intel`
  - market_brief
  - ml_signal
  - top events / live intel 요약

### paper
- `GET /api/paper`
  - 현재 paper session 상태
  - metrics / result / config / ml_signal / fallback 상태 반환

- `POST /api/paper/start`
  - paper session 시작
  - body 예시:
```json
{
  "market_type": "futures",
  "symbol": "BTC/USDT:USDT",
  "timeframe": "15m",
  "strategy": "ensemble_regime",
  "initial_usdt": 1500,
  "position_mode": "both",
  "leverage": 3,
  "mode": "ml_signal",
  "live_refresh_sec": 10
}
```

- `POST /api/paper/pause`
  - paper session 일시정지 및 worker 중단

- `POST /api/paper/reset`
  - paper session 상태 초기화

- `POST /api/paper/config`
  - 현재 paper config 갱신
  - 현재 구현 기준, 새 config로 session을 새로 시작하는 방식으로 반영

- `GET /api/paper/audit`
  - session_id
  - worker pid / alive
  - lock 상태
  - metrics
  - executed strategy/timeframe/position mode
  - consistency
  - runtime_guard
  - config_snapshot / config
  - paper 무결성 및 디버깅용 점검 endpoint

- `GET /api/paper/strategy`
  - BTC/ETH/SOL 목표 비중, 현금 비중, 확정 4시간봉 신호
  - 다음 봉 시가 대기 주문과 강제 리스크 상태

- `GET /api/paper/events?limit=200`
  - SQLite append-only 원장의 주문 대기·거부·체결 이벤트

### account
- `GET /api/account?market_type=futures`
  - 실시간 계정 balance / positions 조회

### risk
- `GET /api/risk`
  - risk_guard
  - execution_policy

### strategy governance
- `POST /api/strategies`
  - 전략 버전, 파라미터, 데이터 기준일, 코드 SHA를 Research 단계로 등록
- `GET /api/strategies`
  - 등록된 전략과 현재 승인 단계 조회
- `GET /api/strategies/{strategy_id}`
  - 전략 재현 정보와 승인·거부·자동 강등 이력
- `POST /api/strategies/{strategy_id}/transition`
  - 한 단계씩만 수동 승격; 기간·거래 수·홀드아웃 Sharpe·낙폭·슬리피지 gate 강제
- `POST /api/strategies/{strategy_id}/demote`
  - 리스크·낙폭·슬리피지 기준 위반 시 한 단계 자동 강등

`small_live`와 `live` 승격에는 실제 거래소 검증 증적이 필수이며, 현재 개발 범위에서는 해당 증적을 생성하지 않는다.

승인 근거 산출은 `strategy_validation.py`가 담당한다. Purged walk-forward,
인과적 시장 국면별 성과, 비용·펀딩 스트레스, Monte Carlo tail risk,
전략 상관관계와 benchmark 초과성과를 생성하며 상세 입력 형식은
`docs/STRATEGY_VALIDATION.md`에 기록되어 있다.

## 현재 paper 엔진 메모
- 기본 모드는 `vol_target_momentum` 이벤트 기반 simulated paper다.
  - BTC/ETH/SOL 기본 비중 60/30/10
  - 200일 EMA와 90일 모멘텀이 모두 양수일 때만 Long
  - 30일 실현 변동성 기준 20% 목표 변동성, 최대 1배 Long/Cash
  - 확정 4시간봉 신호 후 다음 4시간봉 시가 체결
  - 일 1회 또는 목표 비중 대비 5%p 이상 이탈 시 리밸런싱
  - 데이터 지연·잔고 불일치·스프레드·일 손실·낙폭 정책이 주문을 강제로 거부
- 기존 ML/ensemble rolling backtest 모드는 호환 경로로 유지한다.
- 공통 무결성 보강:
  - session_id 도입
  - config snapshot 저장
  - trades / alerts append-only 로그 기반 추가
  - worker lock 기반 동시 write 보호
  - runtime/result consistency 검사
  - config/runtime mismatch 안전 처리
  - paper audit endpoint 추가
  - SQLite append-only 주문 이벤트 원장과 멱등성 키

## 관련 주요 파일
- `backend/app/main.py`
- `backend/app/routes/overview.py`
- `backend/app/routes/intel.py`
- `backend/app/routes/paper.py`
- `backend/app/routes/account.py`
- `backend/app/routes/risk.py`
- `backend/app/services/paper_service.py`
- `paper_live.py`
- `paper_live_runner.py`
- `frontend/app/page.js`
- `frontend/app/intel/page.js`
- `frontend/app/paper/page.js`
- `frontend/app/account/page.js`
- `frontend/app/risk/page.js`
