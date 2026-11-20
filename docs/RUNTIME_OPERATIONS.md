# 데이터 수집과 페이퍼 운영

구현 설계: [RUNTIME_UPGRADE_DESIGN.md](RUNTIME_UPGRADE_DESIGN.md), 이슈 #57.

## 실행 구조

Next.js 웹 3001 → FastAPI 8010 → Python 엔진. 별도 `run_runtime.py`는 공개 시세·뉴스·펀딩과 신호 결과를 수집한다. `paper_live_runner.py`는 사용자가 시작/재개한 모의 세션만 실행한다. Streamlit은 레거시 연구 화면이다.

## 최초 개발환경

Python 3.12, Node 22를 설치한 후 저장소 루트에서:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r research/requirements.txt
npm --prefix frontend ci
# .env가 없을 때만 복사. 기존 설정을 덮어쓰지 않는다.
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe scripts/doctor.py
powershell -File scripts/dev.ps1
```

launcher는 수집기가 종료되면 다시 실행한다. lease가 남은 비정상 종료는 최대 30분 후 복구한다. 중복 프로세스는 lease로 배제한다. PC 종료·절전 중에는 수집할 수 없으므로 상시 운영 시 절전 없는 호스트에서 실행한다. 포트가 이미 사용 중이면 기존 서비스를 임의 종료하지 않고 오류를 표시한다. 종료 시 launcher가 만든 자식만 정리한다.

개별 실행/진단:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010
npm --prefix frontend run dev
.\.venv\Scripts\python.exe run_runtime.py
# 한 사이클 검사
.\.venv\Scripts\python.exe run_runtime.py --once
# 변경 모듈과 전이 의존 테스트만 실행
.\.venv\Scripts\python.exe scripts/test_changed.py --base origin/develop
npm --prefix frontend test
npm --prefix frontend run build
```

일반 빌드는 기존 `.next`를 유지한다. 개발 서버는 `.next-dev`를 사용해 빌드 충돌을 피한다. Windows 권한/OneDrive 문제는 실제 오류 메시지로 진단하며 자동 디렉토리 삭제나 clean build를 수행하지 않는다.

## 설정과 웹 제어

- `.env`: `RUNTIME_DB_PATH=data/runtime.sqlite3`, `SETTINGS_TOKEN` 설정. 비밀값은 커밋하지 않는다.
- `frontend/.env.local`: 필요 시 `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010` 설정. NEXT_PUBLIC 값은 브라우저에 공개되므로 비밀값을 넣지 않는다. 변경 후 웹 재시작/일반 빌드.
- `/operations`: 수집 작업, 실패 원인, 마지막 성공, 다음 재시도, 심볼별 누락 수, 모의 평가, 일별 기록, 신호 결과를 확인한다.
- 설정 토큰을 입력한 뒤 수집 일시정지/재개/재시도 가능. 재시도는 다음 worker 사이클에 적용된다. 프로세스가 없는 상태에서 HTTP 버튼만으로 프로세스를 생성하지 않는다.
- 모의투자 처음 시작은 `/paper`, 기존 세션 재개는 `/operations`. 재개는 동일 session_id/포지션/원장을 보존하고 시세가 준비되지 않으면 409를 반환한다.

## 평가 의미

28일은 유효한 연속 4시간봉 수익률 168개다. 달력상 28일이 지나도 중단 기간은 포함하지 않는다. 60건은 청산 체결 수이며 매수만 반복해 충족할 수 없다. 부분 청산도 청산 체결로 집계한다. 수익률/낙폭은 첫 유효 NAV 관측부터, PF는 비용 포함 실현손익부터 계산한다. 승격 승인과 별개이며 모델이나 실거래를 자동 활성화하지 않는다.

뉴스 점수는 보정된 확률이 아니므로 `intel_shadow`, 전략 목표 비중은 `strategy_shadow`로 기록한다. 검증된 ML 예측만 `ml_shadow`에 기록한다. 이 관측은 공통 4h 체결 격자를 사용하므로 기존 ML 학습 라벨과 동일하다고 간주하지 않는다. 실제 거래용 품질 gate와 분리한다.

관측 시각 이후 첫 4h 시가와 정확한 만기 시가가 모두 수집되어야 결과를 확정한다. 만기 봉 완료까지 추가 지연이 있다. 과거 뉴스의 과거 시점 예측을 새로 만든 것처럼 소급하지 않는다. raw 방향 수익률, 비용 차감 수익률, 확정 라벨을 보관하고 DB 재시작에도 중복 누적하지 않는다.

## 장애 대응

1. 데이터 누락/지연: `/operations` 실패 원인 확인 → 네트워크 복구 → 재시도. 캐시 원본과 이전 NAV는 보존된다.
2. RSS 소스 장애: 해당 소스만 지수 backoff, 다른 소스와 시세는 계속 수집된다. HTTP 404나 DNS 오류를 성공으로 숨기지 않는다.
3. worker 종료: launcher 재실행 또는 `run_runtime.py` 재실행. 중복 lease가 만료되기 전 새 worker가 처리하지 않는다.
4. 모의 worker 장애: runtime watchdog가 running=true인 세션만 복구한다. 수동 pause는 유지한다.
5. 잔고/원장 이상: 기존 원장 무결성·복구 절차(`LEDGER_RECOVERY.md`)를 따른다. 데이터가 없는 자산을 0으로 평가하지 않는다.

SQLite 파일과 `data/paper_sessions`는 운영 데이터다. git에 포함하지 않는다. 데이터 삭제 없이 프로세스를 종료한 후 SQLite backup API를 이용한다.
