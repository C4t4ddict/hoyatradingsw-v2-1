# TradingView 연동 다음 단계 (Webhook + 전략 검증)

## 1) 로컬 서버 실행
```bash
cd /Users/brian/.openclaw/workspace/HoyaTradingSW
source .venv/bin/activate
python main.py
```

헬스체크:
```bash
curl http://127.0.0.1:8000/health
```

---

## 2) TradingView → Webhook 연결
TradingView는 외부에서 접근 가능한 HTTPS URL이 필요합니다.

### 로컬 개발용(권장)
`ngrok` 또는 `cloudflared`로 8000 포트 터널링:

```bash
# ngrok 예시
ngrok http 8000
```

생성된 URL 예시:
`https://abc123.ngrok-free.app/webhook`

이 URL을 TradingView Alert의 **Webhook URL**에 입력.

---

## 3) TradingView Alert 메시지(JSON)
Alert Message에 아래 JSON 템플릿 사용:

```json
{
  "strategy": "ema_cross",
  "symbol": "BTC/USDT:USDT",
  "side": "buy",
  "price": {{close}},
  "stop_loss": {{close}} * 0.99
}
```

> 참고: TradingView 메시지에서 수식 평가가 제한될 수 있습니다. 안정적으로는 `stop_loss`를 서버 기본 로직에 맡기고 생략하는 것을 권장합니다.

수식 없이 안전한 템플릿:

```json
{
  "strategy": "ema_cross",
  "symbol": "BTC/USDT:USDT",
  "side": "buy",
  "price": {{close}}
}
```

---

## 4) 서버 측 사전 검증(완료된 테스트 기준)
다음 호출이 정상 응답해야 함:

```bash
curl -X POST http://127.0.0.1:8000/webhook \
  -H 'Content-Type: application/json' \
  -d '{"strategy":"ema_cross","symbol":"BTC/USDT:USDT","side":"buy","price":100000,"stop_loss":99000}'
```

기대 응답 핵심:
- `accepted: true`
- `order.dry_run: true`
- `risk.position_usdt` 계산값 포함

---

## 5) 전략 검증 체크리스트

### A. 백테스트(TradingView)
- 기간: 최근 6개월 / 1년 각각 실행
- 심볼: BTC, ETH 각각 실행
- Timeframe: 5m / 15m 비교
- 지표 토글:
  - EMA만 ON
  - EMA+RSI ON
  - Breakout ON/OFF
- 확인 지표:
  - Net Profit
  - Max Drawdown
  - Profit Factor
  - Win Rate
  - Trades 수

### B. 웹훅 유효성
- 허용 심볼 외 입력 시 400 에러 나는지
- OFF 전략(`breakout=false`) 호출 시 ignored 처리되는지
- side 값 buy/sell 외 값 거부되는지(추가 검증 필요)

### C. 리스크 검증
- stop_loss를 극단값으로 보냈을 때 position_usdt 0 처리되는지
- min_order_usdt 미만일 때 ignored 되는지
- max_position_usdt 상한이 잘 걸리는지

---

## 6) 실거래 전 필수 작업
1. `.env`에서 `DRY_RUN=true` 유지한 상태로 최소 1~2일 페이퍼 검증
2. API 키 권한 최소화(주문만, 출금 권한 금지)
3. 웹훅 인증 토큰(서버 헤더 검증) 추가
4. 주문/에러 로그 파일 저장 추가
5. 테스트넷 또는 소액으로 단계 전환

---

## 7) 바로 다음 구현 권장
- [ ] `/webhook` 인증 토큰 검증 (`X-Webhook-Token`)
- [ ] `side` 값 strict validation (`buy`/`sell`)
- [ ] 요청/응답 로깅(파일 + timestamp)
- [ ] 전략별 파라미터 분리(config)
- [ ] 간단한 회귀 테스트 스크립트 추가
