import { fetchJson } from '../lib/api'

function fmt(n, suffix = '') {
  const v = Number(n || 0)
  return `${v.toFixed(2)}${suffix}`
}

export default async function Page() {
  let overview = null, paper = null
  try { overview = await fetchJson('/api/overview') } catch {}
  try { paper = await fetchJson('/api/paper') } catch {}

  const s = overview?.summary || {}
  const b = overview?.market_brief || {}
  const m = paper?.metrics || {}
  const ml = overview?.ml_signal || {}
  const d = ml?.decision || {}
  const top = b.top || []
  const pnlClass = Number(m.realized_pnl || s.realized_pnl || 0) >= 0 ? 'good' : 'bad'

  return (
    <>
      <div className="topbar">
        <div>
          <div className="topbar-title">Luminous Intelligence Dashboard</div>
          <div className="topbar-sub">시장 인텔리전스, ML 보조 판단, paper trading 상태를 하나의 컨트롤 센터에서 관리</div>
        </div>
        <div className="chip good">System bias · {(d.bias || b.bias || 'neutral').toUpperCase()}</div>
      </div>

      <h1 className="page-title">Dashboard</h1>
      <p className="page-sub">라이브 인텔을 우선으로 두고 ML 보조 점수와 paper 운영 현황을 연결하는 메인 대시보드</p>

      <div className="grid">
        <div className="card span-3 emphasis"><div className="metric-label">Paper Balance</div><div className="metric-value mono">${fmt(m.virtual_balance)}</div><div className="metric-note">시작 잔액 대비 현재 가상 잔고</div></div>
        <div className="card span-3"><div className="metric-label">Daily / Realized PnL</div><div className={`metric-value mono ${pnlClass}`}>${fmt(m.realized_pnl || s.realized_pnl)}</div><div className="metric-note">실현 손익 기준</div></div>
        <div className="card span-3"><div className="metric-label">Cumulative Return</div><div className="metric-value mono">{fmt(m.return_pct || s.return_pct, '%')}</div><div className="metric-note">누적 수익률</div></div>
        <div className="card span-3"><div className="metric-label">Market Bias</div><div className="metric-value">{(d.bias || b.bias || 'neutral').toUpperCase()}</div><div className="metric-note">ML + live intel 종합 판단</div></div>

        <div className="card span-7 emphasis">
          <div className="split">
            <div>
              <div className="metric-label">Primary Decision</div>
              <div className="metric-value">{(d.bias || 'neutral').toUpperCase()}</div>
              <p className="section-sub">live intel을 우선으로 보고, ML bias와 fallback 상태를 함께 보여주는 핵심 의사결정 카드</p>
            </div>
            <div className="mini-grid" style={{minWidth:280}}>
              <div className="card soft"><div className="metric-label">ML Long</div><div className="metric-value good mono">{fmt(ml?.scores?.long_score)}</div></div>
              <div className="card soft"><div className="metric-label">ML Short</div><div className="metric-value bad mono">{fmt(ml?.scores?.short_score)}</div></div>
              <div className="card soft"><div className="metric-label">Live Long</div><div className="metric-value good mono">{fmt(b.long_score)}</div></div>
              <div className="card soft"><div className="metric-label">Live Short</div><div className="metric-value bad mono">{fmt(b.short_score)}</div></div>
            </div>
          </div>
          <div style={{marginTop:18}}>
            <div className="split">
              <span className="metric-note">Fallback Strategy Status</span>
              <span className="chip warn">{paper?.fallback_mode || 'selector-based fallback'}</span>
            </div>
            <div className="progress" style={{marginTop:10}}><span style={{width:`${Math.min(100, Math.max(8, Number(d.strength || 0) * 100))}%`}} /></div>
          </div>
        </div>

        <div className="card span-5">
          <div className="section-title">Paper Trading Snapshot</div>
          <div className="mini-grid">
            <div><div className="metric-label">Status</div><div className="metric-value">{paper?.running ? 'RUN' : (paper?.paused ? 'PAUSE' : 'STOP')}</div></div>
            <div><div className="metric-label">Executed Strategy</div><div className="metric-value" style={{fontSize:22}}>{paper?.executed_strategy || '-'}</div></div>
            <div><div className="metric-label">Timeframe</div><div className="metric-value" style={{fontSize:22}}>{paper?.executed_timeframe || '-'}</div></div>
            <div><div className="metric-label">Position Mode</div><div className="metric-value" style={{fontSize:22}}>{paper?.executed_position_mode || '-'}</div></div>
          </div>
          <div style={{marginTop:16}} className="metric-note">즉시 반영이 중요한 paper config / symbol / leverage 상태를 운영 관점에서 표시</div>
        </div>

        <div className="card span-8">
          <div className="section-title">Market Intel Preview</div>
          <div className="section-sub">최신 이벤트를 source / topic / long-short 영향 기준으로 스캔</div>
          {top.slice(0, 6).map((item, idx) => (
            <div key={idx} className="feed-item">
              <div className="split">
                <div>
                  <div style={{fontWeight:700, marginBottom:6}}>{item.title || '-'}</div>
                  <div className="metric-note">{item.source || '-'} · {item.topic || '-'} · {item.event_time || item.published || '-'}</div>
                </div>
                <div style={{display:'flex', gap:8}}>
                  <span className="chip good">L {fmt(item.long_event_score)}</span>
                  <span className="chip bad">S {fmt(item.short_event_score)}</span>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="card span-4">
          <div className="section-title">Risk Snapshot</div>
          <div className="metric-label">Open Positions</div>
          <div className="metric-value mono">{s.total_trades || 0}</div>
          <div className="section-sub">실시간 리스크 페이지에서 drawdown / daily loss / 실행 정책을 상세 확인</div>
          <div className="chip warn">Guardrails Active</div>
        </div>

        <div className="card span-12">
          <div className="section-title">Product Narrative</div>
          <div className="section-sub">v2.1은 뉴스·거시·정책·트럼프/코인 발언을 기반으로 양방향 ML 예측을 수행하고, 이를 paper/live 운용 판단으로 연결하는 플랫폼이다.</div>
        </div>
      </div>
    </>
  )
}
