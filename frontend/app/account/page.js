import { fetchJson } from '../../lib/api'

function fmt(n, suffix=''){
  const num = Number(n)
  if (Number.isNaN(num)) return '-'
  return `${num.toFixed(2)}${suffix}`
}

export default async function AccountPage(){
  let data = null
  let paper = null
  try { data = await fetchJson('/api/account?market_type=futures') } catch {}
  try { paper = await fetchJson('/api/paper') } catch {}

  const bal = data?.balance || {}
  const positions = data?.positions || []
  const metrics = paper?.metrics || {}
  const topPositions = positions.slice(0,10)
  const totalPnl = topPositions.reduce((sum, p) => sum + Number(p.unrealizedPnl || 0), 0)

  return (<>
    <div className="topbar">
      <div>
        <div className="topbar-title">Account Overview</div>
        <div className="topbar-sub">실거래 계정 잔고 / 포지션 / paper 성과 요약을 함께 보여주는 account 콘솔</div>
      </div>
      <div className={totalPnl >= 0 ? 'chip good' : 'chip bad'}>Open PnL · {fmt(totalPnl)}</div>
    </div>

    <h1 className="page-title">Account</h1>
    <p className="page-sub">계정 밸런스, 포지션, open pnl, paper performance snapshot을 한 화면에 배치한 overview 페이지</p>

    <div className="grid">
      <div className="card span-3 emphasis"><div className="metric-label">USDT Total</div><div className="metric-value mono">{fmt(bal.usdt_total)}</div><div className="metric-note">선물 계정 총 잔고</div></div>
      <div className="card span-3"><div className="metric-label">USDT Free</div><div className="metric-value mono">{fmt(bal.usdt_free)}</div><div className="metric-note">사용 가능 잔고</div></div>
      <div className="card span-3"><div className="metric-label">USDT Used</div><div className="metric-value mono">{fmt(bal.usdt_used)}</div><div className="metric-note">사용 중인 증거금</div></div>
      <div className="card span-3"><div className="metric-label">Open PnL</div><div className={`metric-value mono ${totalPnl >= 0 ? 'good' : 'bad'}`}>{fmt(totalPnl)}</div><div className="metric-note">상위 포지션 기준 미실현 손익 합계</div></div>

      <div className="card span-8">
        <div className="section-title">Open Positions</div>
        <div className="section-sub">현재 포지션의 side / size / unrealized pnl 상태</div>
        <table className="table">
          <thead><tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Entry</th><th>Mark</th><th>Unrealized PnL</th></tr></thead>
          <tbody>
            {topPositions.map((p,i)=><tr key={i}>
              <td>{p.symbol || '-'}</td>
              <td>{p.side || '-'}</td>
              <td className="mono">{p.contracts || p.positionAmt || '-'}</td>
              <td className="mono">{fmt(p.entryPrice)}</td>
              <td className="mono">{fmt(p.markPrice)}</td>
              <td className={`mono ${Number(p.unrealizedPnl || 0) >= 0 ? 'good' : 'bad'}`}>{fmt(p.unrealizedPnl)}</td>
            </tr>)}
          </tbody>
        </table>
      </div>

      <div className="card span-4">
        <div className="section-title">Paper Snapshot</div>
        <div className="metric-label">Virtual Balance</div><div className="metric-value mono">${fmt(metrics.virtual_balance)}</div>
        <div className="metric-label" style={{marginTop:12}}>Return</div><div className={`metric-value mono ${Number(metrics.return_pct||0)>=0?'good':'bad'}`} style={{fontSize:24}}>{fmt(metrics.return_pct,'%')}</div>
        <div className="metric-label" style={{marginTop:12}}>Realized PnL</div><div className={`metric-value mono ${Number(metrics.realized_pnl||0)>=0?'good':'bad'}`} style={{fontSize:24}}>{fmt(metrics.realized_pnl)}</div>
      </div>

      <div className="card span-12">
        <div className="section-title">Account Narrative</div>
        <div className="section-sub">네가 준 account 시안 구조에 맞춰 계정 overview 성격을 유지하면서, 기존 백엔드의 balance/positions 응답과 paper 성과 데이터를 같이 붙여서 실제 동작하게 연결했다.</div>
      </div>
    </div>
  </>)
}
