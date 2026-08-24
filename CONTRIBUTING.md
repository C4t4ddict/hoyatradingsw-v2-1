# HoyaTradingSW 기여 가이드

이 문서는 `feegachu/fgc`의 협업 규칙을 HoyaTradingSW의 Python/FastAPI/Next.js 구조에 맞게 줄여 적용한 기준입니다.

## 브랜치 전략

| 브랜치 | 역할 |
| --- | --- |
| `main` | 실행·배포 가능한 안정 버전 |
| `develop` | 다음 버전 통합 브랜치 |
| `feature/*` | 신규 기능 |
| `fix/*` | 일반 오류 수정 |
| `chore/*` | 환경, 의존성, 협업 설정 |
| `refactor/*` | 기능 변경 없는 구조 개선 |
| `docs/*` | 문서 변경 |
| `hotfix/*` | `main`의 긴급 수정 |

`main`과 `develop`에는 직접 push하지 않고 Issue 기반 작업 브랜치에서 PR을 생성합니다.

```text
feature/{이슈번호}-{작업내용}
fix/{이슈번호}-{작업내용}
chore/{이슈번호}-{작업내용}
refactor/{이슈번호}-{작업내용}
docs/{이슈번호}-{작업내용}
```

예: `feature/21-paper-order-events`, `fix/24-backtest-fee`, `chore/17-project-setup-conventions`

## 커밋 메시지

Conventional Commits 형식을 사용합니다.

```text
<type>(<scope>): <한글 제목>
```

type은 `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `style`, `perf`, `ci`, `build`를 사용합니다. scope는 다음 프로젝트 영역을 우선 사용합니다.

```text
api, frontend, paper, backtest, ml, intel, exchange, risk, infra, docs
```

예:

```text
feat(paper): 체결 이벤트 로그 조회 API 추가
fix(api): 패키지 import 경로 오류 수정
test(backtest): 수수료 반영 회귀 테스트 추가
docs: 로컬 실행 가이드 보강
```

제목 끝에 마침표를 붙이지 않고 `수정`, `작업 완료`처럼 범위가 불명확한 표현은 피합니다. 본문에는 변경 이유와 검증 결과를 적고 관련 Issue는 `Related to #17` 또는 `Closes #17`로 연결합니다.

## Pull Request

PR 대상은 일반 작업이면 `develop`, 긴급 수정이면 `main`입니다. 제목 형식은 다음과 같습니다.

```text
[Feat] #21 paper 체결 이벤트 로그 추가
[Fix] #24 백테스트 수수료 중복 반영 수정
[Chore] #17 로컬 실행 환경과 협업 규칙 정비
```

PR 본문은 `.github/pull_request_template.md`를 사용해 변경 내용, 검증 명령, 거래 안전 영향, 화면 변경을 기록합니다. 일반 작업은 Squash and merge를 기본으로 하며 squash 제목도 커밋 컨벤션을 따릅니다.

## 변경 전후 검증

PowerShell 첫 번째 터미널에서 컴파일과 서버 실행을 확인합니다.

```powershell
.\.venv\Scripts\python.exe -m compileall backend
Get-ChildItem -LiteralPath . -Filter '*.py' -File | ForEach-Object {
  & .\.venv\Scripts\python.exe -m py_compile $_.FullName
}
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010
```

서버가 실행된 동안 두 번째 PowerShell 터미널에서 상태 확인과 프론트엔드 빌드를 실행합니다.

```powershell
Invoke-RestMethod http://127.0.0.1:8010/healthz
Push-Location frontend
npm run build
Pop-Location
```

검증이 끝나면 첫 번째 터미널에서 `Ctrl+C`로 서버를 종료합니다.

전략·리스크·주문 경로 변경에는 정상 입력뿐 아니라 중복 요청, 네트워크 실패, 손실 제한, `DRY_RUN=true` 동작을 확인합니다. 실계좌 API 키, 토큰, `.env`, 거래·계좌 원본 데이터는 커밋하지 않습니다.
