# 데이터·페이퍼·신호 운영 고도화 설계

기준일: 2026-11-19 (KST). 상태: 구현 전 설계. 변경 범위는 이 문서의 R1–R7로 추적한다.

## 1. 현재 구조와 목표

Next.js 웹(3001) → FastAPI(8010) → Python 전략/페이퍼 엔진 → SQLite 원장 구조다. Streamlit은 레거시 연구 화면으로 유지한다. 기존 CI, 안전 제어, 원장 복구, ML 품질 게이트를 재사용한다.

목표는 공개 데이터 수집, 지속 가능한 모의 운용, 예측 당시 값과 후행 결과의 연결, 재현 가능한 개발환경이다. 긴 ML 학습/모델 선정, 모바일, 인증 거래소 주문 검증은 이번 범위에서 제외한다. 데이터 수집은 공개 API만 호출한다. 자동화는 paper/실계좌 설정을 변경하지 않는다.

## 2. 요구사항 및 완료 기준

| ID | 기능 | 완료 기준 |
|---|---|---|
| R1 | 공개 캔들 수집/복구 | BTC·ETH·SOL 현물 4h 1,400봉 보관, 완료 봉만 채택, OHLCV 유효성 검사, 중복 제거, 내부/선두/말미 누락 탐지, 가장 오래된 누락부터 페이지네이션, 실패해도 기존 데이터 보존 |
| R2 | 뉴스·펀딩 수집 | 뉴스 원문 이벤트 증분 저장, BTC 무기한 펀딩 이력 저장, 소스별 최종 성공/오류/연속 실패/다음 시도 표시, 개별 실패가 다른 작업을 막지 않음 |
| R3 | 지속 실행/복구 | SQLite 임대 잠금으로 한 worker만 실행, 주기적 heartbeat, 제한된 지수 재시도, 재실행 시 저장된 작업 재개, 설정 토큰으로 일시정지/재개/재시도, 재학습 없이 동작 |
| R4 | 페이퍼 캠페인 | 세션별 28일·60회 청산 체결 관찰 진행률, 일별 비용 포함 NAV·수익률·Sharpe·MDD·PF·수수료·체결 수 저장, 부족 데이터/중단 시간 표시, 기간 경과만으로 성공 판정 금지 |
| R5 | 신호 결과 | 의사결정 시점·종류·심볼·버전·확률·기간·비용을 불변 저장; 이후 처음 관측 가능한 4h 시가와 정확한 만기 시가로 라벨링; 지연/미래/가격 누락은 대기; 중복 처리 불가; 품질 저장소 연결 |
| R6 | API/웹 | 운영 화면에 데이터·작업·캠페인·신호 요약과 제어 버튼; freshness와 오류를 숨기지 않음; 재개는 기존 paper 세션 보존; API 주소 환경변수화 |
| R7 | 개발환경/CI | Python 3.12·Node 22 기준, .venv 실행 launcher와 doctor, frontend 독립 dev/build 출력, backend/frontend 테스트 및 빌드 CI, 설정 예시·운영 가이드 |

## 3. 데이터와 상태

새 `data/runtime.sqlite3`는 기존 원장과 분리한다. WAL, busy timeout, 트랜잭션을 사용한다. 캔들 키는 `(symbol,timeframe,timestamp)`; 펀딩 키는 `(symbol,timestamp)`다. 원시 응답의 중복은 upsert하며 미완성/비정상 가격은 저장하지 않는다.

`jobs`: 작업명, 최근 시도/성공, 오류 유형과 마스킹된 메시지, 연속 실패, 다음 실행. `worker`: singleton lease owner/expiry/heartbeat와 enabled flag. 재시도 요청은 next_run을 앞당긴다. UI는 worker heartbeat와 enabled를 따로 표시한다.

`observations`: 결정 ID, signal_type, symbol, observed_at, horizon(4h/24h), direction, predicted_probability(없으면 null), signed_score, source/version, round_trip_cost, pending/resolved 상태, entry/exit, gross/net return. ID는 신호 원천+모델 버전+시간+심볼+기간의 해시다. 변경된 과거 예측으로 덮어쓰지 않는다.

`paper_samples`: 세션·확정 봉 시각을 고유 키로 NAV를 저장한다. 동일 봉에서 주기적으로 재관측해도 표본 수가 늘지 않는다. `paper_fills`: 전체 체결 ID, 시각, 방향, 수수료, 실현손익. `paper_daily`: UTC 일자별 요약. 사용자 화면은 UTC 기준임을 명시한다.

## 4. 수집 및 복구 알고리즘

1. 최신 완료 봉 끝 시각을 UTC로 고정하고 1,400개 예상 timestamp를 구성한다.
2. DB와 비교해 가장 오래된 누락을 찾고 해당 위치부터 최대 1,000개씩 공개 OHLCV를 받는다.
3. timestamp 정렬·중복·유한값·양의 OHLC·고저 범위·비음수 거래량을 검증하고 완료 봉만 저장한다. 한 사이클 요청 수를 제한한다.
4. 캐시가 완전하면 새 봉 경계까지 요청하지 않는다. 누락/지연이면 ready=false다. 캐시를 다른 거래소 가격으로 조용히 대체하지 않는다.
5. 각 job 실패 시 저장 데이터는 보존하고 지수 backoff(상한 1시간)를 기록한다. worker는 다른 job을 계속한다.
6. 중복 worker는 SQLite 임대로 차단하고 종료 시 자신의 임대만 해제한다. 네트워크 timeout과 재시도 시간을 임대보다 짧게 제한한다.

뉴스는 원문 이벤트와 수집 성공 시각을 따로 보관한다. 뉴스 방향 점수는 검증된 확률이 아니므로 `intel_shadow` 관측으로 분리하고 기존 `intel` 거래 gate를 자동 활성화하지 않는다. ML 예측은 검증된 실제 예측만 기록하며 fallback 0.5는 기록하지 않는다. 모델 재학습은 호출하지 않는다.

## 5. 페이퍼와 결과 추적

페이퍼 기본 엔진은 공유 캔들 캐시를 소비한다. 데이터가 불완전/지연이면 새 주문/체결을 진행하지 않고 이전 NAV를 보존한다. 재개는 동일 session_id와 원장을 복원한다. 누락된 시기에 가상의 체결을 만들지 않는다.

평가의 60거래는 단순 매수 체결이 아니라 실현손익이 있는 청산 체결 수다. 28일은 유효 관측 봉 수 × 4h로 산정하고 달력상 경과일과 분리한다. 표본 간 간격이 4h보다 큰 경우 연속 수익률에 섞지 않는다. Sharpe는 연속 4h 수익률의 연율화, MDD는 관측 NAV 최고점 대비 낙폭, PF는 비용 포함 청산 손익의 이익합/손실합이다. 손실/표본 부족은 null로 표시한다. 관측 조건 충족은 `ready_for_review`이며 자동 live 승격이 아니다.

신호 라벨은 observed_at 이후 첫 봉 시가를 진입점으로 사용한다. 정확한 종료 봉이 없으면 대기하고 다음 임의 가격으로 대체하지 않는다. 만기 봉도 완료된 뒤 라벨 확정한다. 방향 수익률에서 왕복 비용을 차감한다. 확률이 있는 검증 모델은 SignalQualityStore에 멱등 기록하고 전략/뉴스 휴리스틱은 별도 관측 유형으로 유지한다.

## 6. API와 화면

- `GET /api/runtime`: worker, job, 데이터 품질, campaign, 신호 pending/resolved와 최근 기록.
- `POST /api/runtime/control`: action=`pause|resume|retry`, X-Settings-Token 필수. resume는 수집 scheduler만 재개.
- `POST /api/paper/resume`: 설정 토큰 필수, 기존 세션 재개.
- 운영·보안 화면: 수집 상태/누락/최근 시각, 작업 실패·다음 시도, 캠페인 관찰·청산 진행률, 신호 결과·순수익과 대기 상태. 15초 재조회, 오류 표시, 요청 중 버튼 중복 방지.
- 프론트 API 주소는 `NEXT_PUBLIC_API_BASE_URL`로 통일한다.

## 7. 개발환경

`.python-version`, `.nvmrc`, frontend lockfile을 기준으로 실행한다. `scripts/dev.ps1`은 프로젝트 .venv Python을 명시하며 backend/frontend/collector를 실행하고 자식 프로세스 종료를 정리한다. collector 장애는 재시작하되 임대 잠금을 따른다. `.next-dev`와 `.next`를 분리해 dev/build 충돌을 줄인다. OneDrive의 파일 권한 오류를 코드 결함으로 단정하지 않고 별도 진단한다.

`scripts/doctor.py`는 버전·의존성·DB 접근·환경 설정 존재 여부만 출력한다. 비밀값은 출력하지 않는다. CI에 runtime 회귀 테스트, API 인증 테스트, frontend 설정 테스트를 포함한다.

## 8. 검증 계획

가짜 거래소와 고정 UTC 시각을 사용해 누락 백필·페이지네이션·진행 정지·미완성 봉·NaN·네트워크 실패·재시도·임대 충돌을 검증한다. 신호는 만기 전 대기·정확한 진입/종료·중복·미래 예측 거부·비용 계산을 검증한다. 캠페인은 200건 초과 체결 보존·세션 분리·단순 달력 경과 차단·유효 관찰일·일간 요약을 검증한다.

기존 전체 Python 테스트와 Next production build를 통과해야 한다. 공개 API 한 사이클 smoke test와 backend GET endpoint 확인을 수행한다. 28일 관측 완료나 전략 수익성은 구현 완료와 구분해서 보고한다.

## 9. 변경/병합 순서

설계 커밋 → R1–R3 데이터/worker → R4–R5 평가/결과 → R6 화면/API → R7 환경/문서/회귀 테스트 → CI 확인 → 일반 merge. Issue 기반 feature 브랜치, Conventional Commit 한글 제목과 저장소 PR 템플릿을 사용한다. 사용자 지시에 따라 리뷰 승인을 필수 gate로 두지 않으며 squash를 사용하지 않는다.
