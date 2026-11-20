# Goldman Sachs `gs-quant` 적용 판단

검토 기준일: 2026-08-25 KST (2026-08-24 UTC)

## 결론

`gs-quant`를 현재 실시간 거래 경로에 바로 의존시키는 것은 권장하지 않는다. HoyaTradingSW는 Binance/CCXT 기반 암호화폐 현물·선물 운영 도구인 반면, `gs-quant`의 강점은 기관용 파생상품 표현, 리스크, 포트폴리오, Goldman Sachs Marquee 데이터/API에 있다.

다만 연구·검증 계층에서는 선택적으로 가치가 있다. 시계열 통계, 이벤트 스터디, 포트폴리오·시나리오 모델의 설계를 참고하고, 구체적인 지표 하나를 독립된 연구 환경에서 비교 검증하는 방식이 적합하다.

## 확인한 사실

- 공식 저장소: https://github.com/goldmansachs/gs-quant
- 용도: 정량 전략, 파생상품 구조화·가격·리스크, 포트폴리오 분석용 Python 툴킷
- 라이선스: Apache-2.0
- Python: 공식 `pyproject.toml` 기준 3.10 이상, 3.12 지원
- 주요 영역: `timeseries`, `backtests`, `risk`, `markets`, `instrument`, `analytics`
- Marquee 데이터와 일부 API 기능은 Goldman Sachs의 client id/secret이 필요하다.

### 재현 정보

- 평가 리비전: `goldmansachs/gs-quant@02490b047a3b8db28723cb520be96ee5fc5423c5`
- 평가 패키지: `gs-quant==2.1.4`
- 환경: Python 3.12, HoyaTradingSW `requirements.txt` 설치 환경
- 확인 명령: `python -m pip install --dry-run gs-quant==2.1.4`
- 새로 해석된 패키지: `aenum==3.1.17`, `asteval==1.0.10`, `backoff==2.2.1`, `dataclasses-json==0.6.7`, `deprecation==2.1.0`, `dill==0.4.1`, `gs-quant==2.1.4`, `httpcore==1.0.9`, `httpx==0.28.1`, `inflection==0.5.1`, `lmfit==1.3.4`, `marshmallow==3.26.2`, `more-itertools==11.1.0`, `msgpack==1.2.1`, `mypy-extensions==1.1.0`, `nest-asyncio==1.6.0`, `numpy==2.3.5`, `opentelemetry-api==1.44.0`, `opentelemetry-sdk==1.44.0`, `opentelemetry-semantic-conventions==0.65b0`, `patsy==1.0.2`, `pydash==6.0.2`, `statsmodels==0.14.6`, `tqdm==4.70.0`, `typing-inspect==0.9.0`, `uncertainties==3.2.3`, `websockets==17.0.1`
- 기존 환경에서 재사용된 주요 패키지: `cachetools==6.2.6`, `certifi==2026.7.22`, `pandas==2.3.1`, `python-dateutil==2.9.0.post0`, `scipy==1.18.1`, `PyYAML==6.0.2`, `requests==2.34.2`, `anyio==4.14.2`, `idna==3.19`, `h11==0.16.0`, `pytz==2026.3.post1`, `tzdata==2026.3`, `six==1.17.0`, `packaging==25.0`, `typing-extensions==4.16.0`, `charset-normalizer==3.5.1`, `urllib3==2.7.0`, `colorama==0.4.6`

## 현재 프로젝트와의 적합성

| 영역 | 적합도 | 판단 |
| --- | --- | --- |
| Binance 주문·체결 | 낮음 | CCXT 기반 기존 경로가 더 직접적이다. |
| 암호화폐 백테스트 | 보통 | 엔진 교체보다 통계·검증 아이디어 참고가 낫다. |
| 시계열/계량 분석 | 높음 | 수익률, 변동성, 상관, 이벤트 연구 비교에 활용 가능하다. |
| 파생상품 가격·Greeks | 보통 | 옵션 거래 기능을 추가할 때 가치가 커진다. |
| 기관 포트폴리오·리스크 | 보통~높음 | 다자산 확장 시 시나리오·리스크 표현을 참고할 수 있다. |
| 실시간 운영 의존성 | 낮음 | 외부 인증, 의존성 규모, 장애 전파 위험이 있다. |

현재 `requirements.txt` 설치 결과는 NumPy 2.5 계열을 허용하지만 `gs-quant`는 NumPy `<2.4.0`을 요구한다. 직접 추가하면 환경 해석 결과가 바뀌며 `statsmodels`, `lmfit`, OpenTelemetry 등 추가 의존성도 들어온다. 운영 환경에 즉시 섞지 말아야 하는 실무적 이유다.

## 권장 적용 순서

1. 현재 백테스트 결과에 CAGR, 최대 낙폭, Sharpe/Sortino, turnover, fee·funding 민감도를 일관된 스키마로 저장한다.
2. `research/` 또는 별도 가상환경에 `gs-quant` 실험을 격리한다.
3. 첫 실험은 Marquee 인증이 필요 없는 시계열 지표 하나로 제한하고 기존 계산과 golden dataset으로 비교한다.
4. 값·성능·설명 가능성이 개선될 때만 `quant_adapter` 인터페이스 뒤에 선택 기능으로 둔다.
5. 실시간 주문 결정 경로에는 충분한 회귀·장애 테스트 전까지 연결하지 않는다.

후보 PoC는 뉴스/거시 이벤트 전후 BTC 수익률의 이벤트 스터디다. HoyaTradingSW의 `market_intel` 이벤트와 OHLCV를 입력으로 사용해 이벤트 창 수익률·변동성 변화를 계산하면 기존 인텔 점수의 근거를 검증할 수 있다. 이 방식은 GS 전용 데이터 없이도 실질적 가치를 시험할 수 있다.

## 도입 시 안전장치

- `gs-quant` 버전과 연구용 의존성을 운영 requirements와 분리한다.
- 동일 입력·시점·수수료 조건을 고정한 회귀 데이터셋을 둔다.
- 모든 계산 결과에 라이브러리 버전, 파라미터, 데이터 구간을 기록한다.
- 라이브러리 오류나 인증 실패가 주문 엔진으로 전파되지 않도록 adapter 경계를 둔다.
- 소스 코드를 복사·수정해 배포하면 Apache-2.0의 LICENSE/NOTICE 조건을 확인한다.
