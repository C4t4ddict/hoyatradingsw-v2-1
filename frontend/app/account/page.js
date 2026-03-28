import { fetchJson } from '../../lib/api'
export default async function AccountPage(){
  let data = null
  try { data = await fetchJson('/api/account?market_type=futures') } catch {}
  const bal = data?.balance || {}
  const positions = data?.positions || []
  return (<><h1 className="page-title">실시간 계정</h1><p className="page-sub">실거래 계정/포지션/손익 상태</p><div className="grid"><div className="card span-4"><div className="metric-label">USDT Total</div><div className="metric-value">{bal.usdt_total ?? '-'}</div></div><div className="card span-4"><div className="metric-label">USDT Free</div><div className="metric-value">{bal.usdt_free ?? '-'}</div></div><div className="card span-4"><div className="metric-label">USDT Used</div><div className="metric-value">{bal.usdt_used ?? '-'}</div></div><div className="card span-12"><div className="section-title">포지션</div><table className="table"><thead><tr><th>심볼</th><th>방향</th><th>수량</th><th>미실현손익</th></tr></thead><tbody>{positions.slice(0,10).map((p,i)=><tr key={i}><td>{p.symbol||'-'}</td><td>{p.side||'-'}</td><td>{p.contracts||p.positionAmt||'-'}</td><td>{p.unrealizedPnl||'-'}</td></tr>)}</tbody></table></div></div></>) }
