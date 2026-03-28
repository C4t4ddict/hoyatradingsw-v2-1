import { fetchJson } from '../lib/api'
export default async function Page(){
  let overview = null, paper = null
  try { overview = await fetchJson('/api/overview') } catch {}
  try { paper = await fetchJson('/api/paper') } catch {}
  const s = overview?.summary || {}
  const b = overview?.market_brief || {}
  const m = paper?.metrics || {}
  return (<><h1 className="page-title">개요</h1><p className="page-sub">시장 인텔리전스와 ML 보조 판단 기반 운용 대시보드</p><div className="grid"><div className="card span-3"><div className="metric-label">누적 수익률</div><div className="metric-value">{Number(s.return_pct || 0).toFixed(2)}%</div></div><div className="card span-3"><div className="metric-label">실현손익</div><div className="metric-value">{Number(s.realized_pnl || 0).toFixed(2)}</div></div><div className="card span-3"><div className="metric-label">Paper 잔고</div><div className="metric-value">{Number(m.virtual_balance || 0).toFixed(2)}</div></div><div className="card span-3"><div className="metric-label">시장 바이어스</div><div className="metric-value">{b.bias || 'neutral'}</div></div><div className="card span-4"><div className="metric-label">총 체결</div><div className="metric-value">{s.total_trades || 0}</div></div><div className="card span-4"><div className="metric-label">Paper 수익률</div><div className="metric-value">{Number(m.return_pct || 0).toFixed(2)}%</div></div><div className="card span-4"><div className="metric-label">최종 시그널</div><div className="metric-value">{b.signal || '중립'}</div></div><div className="card span-12"><div className="section-title">요약</div><p>v2.1은 Streamlit UI를 걷어내고 FastAPI + Next.js 구조로 이관 중입니다. 개요/모의투자/시장 인텔/계정/리스크 화면을 순차적으로 실제 API와 연결하고 있습니다.</p></div></div></>)
}
