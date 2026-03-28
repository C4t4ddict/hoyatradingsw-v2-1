# HoyaTradingSW v2.1

- 목표: Streamlit UI에서 FastAPI + Next.js UI 구조로 이관
- 방향: 토스 스타일 UX, 모의투자/시장 인텔/실시간 계정 중심
- 기존 엔진: 유지
- UI: frontend/Next.js
- API: backend/FastAPI

## 실행
### backend
```bash
cd backend/app
uvicorn main:app --reload --port 8010
```

### frontend
```bash
cd frontend
npm install
npm run dev
```
