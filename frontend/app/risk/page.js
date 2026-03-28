import { fetchJson } from '../../lib/api'
export default async function RiskPage(){
  let data = null
  try { data = await fetchJson('/api/risk') } catch {}
  const g = data?.risk_guard || {}
  const ep = data?.execution_policy || {}
  return (<><h1 className="page-title">리스크 가드</h1><p className="page-sub">손실 제한, 연속 손실, 동시 포지션 제한</p><div className="grid"><div className="card span-6"><div className="section-title">Spot</div><pre>{JSON.stringify(g.spot || {}, null, 2)}</pre></div><div className="card span-6"><div className="section-title">Futures</div><pre>{JSON.stringify(g.futures || {}, null, 2)}</pre></div><div className="card span-12"><div className="section-title">실행 정책</div><pre>{JSON.stringify(ep || {}, null, 2)}</pre></div></div></>) }
