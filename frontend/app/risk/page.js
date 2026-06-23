import { fetchJson } from '../../lib/api'

function Row({label, value, className=''}){
  return <tr><td>{label}</td><td className={className}>{String(value ?? '-')}</td></tr>
}

export default async function RiskPage(){
  let data = null
  try { data = await fetchJson('/api/risk') } catch {}
  const g = data?.risk_guard || {}
  const spot = g.spot || {}
  const futures = g.futures || {}
  const ep = data?.execution_policy || {}
  const warnings = [
    !futures.enabled ? 'futures risk guard disabled' : null,
    !spot.enabled ? 'spot risk guard disabled' : null,
    futures.max_leverage ? `max leverage ${futures.max_leverage}` : null,
    futures.allow_short === false ? 'short disabled' : null,
  ].filter(Boolean)

  return (<>
    <div className="topbar">
      <div>
        <div className="topbar-title">Risk Control Intelligence</div>
        <div className="topbar-sub">손실 제한, 연속 손실, 포지션 제한, 실행 정책을 운영 관점에서 보여주는 리스크 페이지</div>
      </div>
      <div className="chip warn">Guardrails Active</div>
    </div>

    <h1 className="page-title">Risk Control</h1>
    <p className="page-sub">drawdown / daily loss / leverage / position limit / execution policy를 한 화면에서 읽는 리스크 제어 콘솔</p>

    <div className="grid">
      <div className="card span-3 emphasis"><div className="metric-label">Spot Guard</div><div className="metric-value">{spot.enabled ? 'ON' : 'OFF'}</div><div className="metric-note">spot risk guard 상태</div></div>
      <div className="card span-3"><div className="metric-label">Futures Guard</div><div className="metric-value">{futures.enabled ? 'ON' : 'OFF'}</div><div className="metric-note">futures risk guard 상태</div></div>
      <div className="card span-3"><div className="metric-label">Max Leverage</div><div className="metric-value mono">{futures.max_leverage ?? '-'}</div><div className="metric-note">허용 최대 레버리지</div></div>
      <div className="card span-3"><div className="metric-label">Short Policy</div><div className="metric-value">{futures.allow_short ? 'ALLOW' : 'BLOCK'}</div><div className="metric-note">futures short 허용 여부</div></div>

      <div className="card span-6">
        <div className="section-title">Spot Risk Guardrail</div>
        <table className="table"><tbody>
          <Row label="enabled" value={spot.enabled} className={spot.enabled ? 'good mono' : 'bad mono'} />
          <Row label="daily_loss_limit_pct" value={spot.daily_loss_limit_pct} className="mono" />
          <Row label="max_consecutive_losses" value={spot.max_consecutive_losses} className="mono" />
          <Row label="max_open_positions" value={spot.max_open_positions} className="mono" />
        </tbody></table>
      </div>

      <div className="card span-6">
        <div className="section-title">Futures Risk Guardrail</div>
        <table className="table"><tbody>
          <Row label="enabled" value={futures.enabled} className={futures.enabled ? 'good mono' : 'bad mono'} />
          <Row label="daily_loss_limit_pct" value={futures.daily_loss_limit_pct} className="mono" />
          <Row label="max_consecutive_losses" value={futures.max_consecutive_losses} className="mono" />
          <Row label="max_open_positions" value={futures.max_open_positions} className="mono" />
          <Row label="max_leverage" value={futures.max_leverage} className="mono" />
          <Row label="allow_short" value={futures.allow_short} className={futures.allow_short ? 'good mono' : 'bad mono'} />
        </tbody></table>
      </div>

      <div className="card span-4">
        <div className="section-title">Warnings / Attention</div>
        <div className="section-sub">현재 실행 정책에서 주의해서 봐야 할 항목</div>
        <div style={{display:'flex', flexDirection:'column', gap:10}}>
          {warnings.length ? warnings.map((w,i)=><div key={i} className="chip warn">{w}</div>) : <div className="chip good">No immediate warnings</div>}
        </div>
      </div>

      <div className="card span-8">
        <div className="section-title">Execution Policy</div>
        <div className="section-sub">현재 백엔드 execution policy 응답을 그대로 반영</div>
        <table className="table"><tbody>
          {Object.entries(ep).map(([k,v])=><Row key={k} label={k} value={typeof v === 'object' ? JSON.stringify(v) : v} className="mono" />)}
        </tbody></table>
      </div>

      <div className="card span-12">
        <div className="section-title">Risk Narrative</div>
        <div className="section-sub">이 페이지는 단순 수치 나열이 아니라, daily loss / consecutive losses / leverage / short allowance / execution policy를 함께 보여줘서 운용 안정성을 빠르게 판단하도록 설계했다.</div>
      </div>
    </div>
  </>)
}
