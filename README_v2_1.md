# HoyaTradingSW v2.1

- 목표: Streamlit UI에서 FastAPI + Next.js UI 구조로 이관
- 방향: 토스 스타일 UX, 모의투자/시장 인텔/실시간 계정 중심
- 기존 엔진: 유지
- UI: `frontend/` Next.js
- API: `backend/` FastAPI

## 실행
### backend
```bash
cd /Users/brian/.openclaw/workspace/hoyatradingsw-v2-1
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8010
```

### frontend
```bash
cd /Users/brian/.openclaw/workspace/hoyatradingsw-v2-1/frontend
npm install
npm run dev
```

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

### account
- `GET /api/account?market_type=futures`
  - 실시간 계정 balance / positions 조회

### risk
- `GET /api/risk`
  - risk_guard
  - execution_policy

## 현재 paper 엔진 메모
- 현재 paper trading은 완전한 event-driven 실시간 체결 엔진이라기보다 rolling backtest 기반 simulated paper에 가깝다.
- 대신 최근 작업으로 아래 보강이 들어갔다.
  - session_id 도입
  - config snapshot 저장
  - trades / alerts append-only 로그 기반 추가
  - worker lock 기반 동시 write 보호
  - runtime/result consistency 검사
  - config/runtime mismatch 안전 처리
  - paper audit endpoint 추가

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
