'use client'
import { useEffect, useMemo, useState } from 'react'

const BASE = 'http://127.0.0.1:8010'

function fmt(n, suffix='') { return n===null||n===undefined||n==='' ? '-' : `${Number(n).toFixed(2)}${suffix}` }

export default function PaperPage(){
  const [data,setData]=useState(null)
  const [loading,setLoading]=useState(false)
  const [initialUsdt,setInitialUsdt]=useState(1000)
  const [targetVolatility,setTargetVolatility]=useState(20)

  const load=async()=>{ const r=await fetch(`${BASE}/api/paper`,{cache:'no-store'}); const j=await r.json(); setData(j); return j }
  useEffect(()=>{ load().then((j)=>{
    const cfg=j?.config||{}
    if (cfg.initial_usdt != null) setInitialUsdt(cfg.initial_usdt)
    if (cfg.target_volatility != null) setTargetVolatility(Number(cfg.target_volatility)*100)
  }) },[])

  const call=async(path, body=null)=>{
    setLoading(true)
    await fetch(`${BASE}${path}`,{method:'POST', headers:{'Content-Type':'application/json'}, body: body ? JSON.stringify(body) : null})
    const j = await load()
    const cfg=j?.config||{}
    if (cfg.initial_usdt != null) setInitialUsdt(cfg.initial_usdt)
    if (cfg.target_volatility != null) setTargetVolatility(Number(cfg.target_volatility)*100)
    setLoading(false)
  }

  const applyConfig=async()=>{
    await call('/api/paper/config', {
      market_type:'spot', symbol:'BTC/ETH/SOL', leverage:1,
      initial_usdt:Number(initialUsdt),
      target_volatility:Number(targetVolatility)/100,
      strategy:'vol_target_momentum', mode:'vol_target_momentum', timeframe:'4h', position_mode:'long_cash',
    })
  }

  const startPaper=async()=>{
    await call('/api/paper/start', {
      ...(data?.config || {}),
      market_type:'spot', symbol:'BTC/ETH/SOL',
      initial_usdt:Number(initialUsdt),
      leverage:1, target_volatility:Number(targetVolatility)/100,
      strategy:'vol_target_momentum', mode:'vol_target_momentum', timeframe:'4h', position_mode:'long_cash',
    })
  }

  const m=data?.metrics||{}
  const cfg=data?.config||{}
  const trades=(data?.result?.trades)||[]
  const d=data?.ml_signal?.decision||{}
  const s=data?.ml_signal?.scores||{}
  const note=data?.paper_note||''
  const latestTrade = trades.length ? trades[trades.length - 1] : null
  const decision=data?.strategy_decision||{}
  const targets=decision?.target_weights||{}
  const riskStatus=data?.risk_status||{}
  const marketRegime=data?.market_regime||{}
  const orderEvents=data?.order_events||[]
  const runningState = data?.running ? 'RUN' : (data?.paused ? 'PAUSE':'STOP')
  const latestTradePnlClass = Number(latestTrade?.pnl || 0) >= 0 ? 'good' : 'bad'

  const positionSummary = useMemo(() => ({
    side: latestTrade?.side || 'CASH',
    entry: fmt(latestTrade?.entry),
    exit: fmt(latestTrade?.exit),
    pnl: fmt(latestTrade?.pnl),
    pnlPct: fmt(latestTrade?.pnl_pct, '%'),
  }), [latestTrade])

  return (<>
    <div className="topbar">
      <div>
        <div className="topbar-title">Paper Trading Operations</div>
        <div className="topbar-sub">검증된 고정 universe와 변동성 목표, 세션 상태를 관리하는 paper trading 운영 콘솔</div>
      </div>
      <div className={`chip ${runningState === 'RUN' ? 'good' : runningState === 'PAUSE' ? 'warn' : 'bad'}`}>{runningState}</div>
    </div>

    <h1 className="page-title">Paper Trading</h1>
    <p className="page-sub">확정 4시간봉 기반 BTC/ETH/SOL long/cash 변동성 타기팅 가상 운용을 제어하고 감사하는 페이지</p>

    <div className="grid">
      <div className="card span-4 emphasis">
        <div className="metric-label">Current Session</div>
        <div className="metric-value">{runningState}</div>
        <div className="section-sub">현재 paper session 상태와 최신 운용 모드</div>
        <div style={{display:'flex', gap:8, flexWrap:'wrap'}}>
          <span className="chip">{data?.executed_strategy || cfg.strategy || '-'}</span>
          <span className="chip">{data?.executed_timeframe || cfg.timeframe || '-'}</span>
          <span className="chip warn">{data?.fallback_mode || 'inactive'}</span>
        </div>
      </div>

      <div className="card span-4">
        <div className="metric-label">Virtual Balance</div>
        <div className="metric-value mono">${fmt(m.virtual_balance)}</div>
        <div className="metric-note">시작 잔액 대비 현재 가상 잔고</div>
      </div>

      <div className="card span-4">
        <div className="metric-label">Advisory Bias</div>
        <div className="metric-value">{(d.bias || 'neutral').toUpperCase()}</div>
        <div className="metric-note">운영 참고용이며 vol-target 주문 방향을 직접 결정하지 않음</div>
      </div>

      <div className="card span-6">
        <div className="section-title">Config Panel</div>
        <div className="section-sub">실행 엔진과 동일한 BTC/ETH/SOL · spot · 4h · long/cash · 1x 설정만 제공</div>
        <div className="mini-grid">
          <div>
            <div className="metric-label">Universe</div>
            <div className="metric-note mono">BTC / ETH / SOL</div>
          </div>
          <div>
            <div className="metric-label">Leverage / Direction</div>
            <div className="metric-note mono">1x / LONG-CASH</div>
          </div>
          <div>
            <div className="metric-label">Starting Balance</div>
            <input type="number" value={initialUsdt} onChange={e=>setInitialUsdt(e.target.value)} />
          </div>
          <div>
            <div className="metric-label">Target Volatility %</div>
            <input type="number" min="1" max="25" value={targetVolatility} onChange={e=>setTargetVolatility(e.target.value)} />
          </div>
        </div>
        <div className="button-row" style={{marginTop:16}}>
          <button onClick={startPaper} disabled={loading}>시작</button>
          <button onClick={applyConfig} disabled={loading}>즉시 반영</button>
          <button onClick={()=>call('/api/paper/pause')} disabled={loading}>일시정지</button>
          <button onClick={()=>call('/api/paper/reset')} disabled={loading}>리셋</button>
          <button onClick={load} disabled={loading}>새로고침</button>
        </div>
      </div>

      <div className="card span-6">
        <div className="section-title">Current Position Snapshot</div>
        <div className="mini-grid">
          <div><div className="metric-label">Side</div><div className="metric-value" style={{fontSize:24}}>{positionSummary.side}</div></div>
          <div><div className="metric-label">Leverage</div><div className="metric-value mono" style={{fontSize:24}}>1.00x</div></div>
          <div><div className="metric-label">Entry</div><div className="metric-value mono" style={{fontSize:24}}>{positionSummary.entry}</div></div>
          <div><div className="metric-label">Exit / Current</div><div className="metric-value mono" style={{fontSize:24}}>{positionSummary.exit}</div></div>
          <div><div className="metric-label">PnL $</div><div className={`metric-value mono ${latestTradePnlClass}`} style={{fontSize:24}}>{positionSummary.pnl}</div></div>
          <div><div className="metric-label">PnL %</div><div className={`metric-value mono ${latestTradePnlClass}`} style={{fontSize:24}}>{positionSummary.pnlPct}</div></div>
        </div>
      </div>

      <div className="card span-4">
        <div className="section-title">Advisory Signal Stack</div>
        <div className="metric-label">Long Score</div><div className="metric-value good mono">{fmt(s.long_score)}</div>
        <div className="metric-label" style={{marginTop:12}}>Short Score</div><div className="metric-value bad mono">{fmt(s.short_score)}</div>
      </div>

      <div className="card span-8">
        <div className="section-title">Telegram Alert Preview</div>
        <div className="section-sub">최근 체결 결과를 알림 메시지 형식으로 미리 보는 카드</div>
        <div className="card soft">
          <div style={{fontWeight:800, marginBottom:10}}>📡 Paper Trade Alert</div>
          <div className="metric-note mono">시작 잔액: ${fmt(m.starting_balance ?? initialUsdt)}</div>
          <div className="metric-note mono">진입/청산: {positionSummary.entry} → {positionSummary.exit}</div>
          <div className={`metric-note mono ${latestTradePnlClass}`}>손익 $: {positionSummary.pnl}</div>
          <div className={`metric-note mono ${latestTradePnlClass}`}>손익 %: {positionSummary.pnlPct}</div>
          <div className="metric-note mono">종료 잔액: ${fmt(m.virtual_balance)}</div>
        </div>
      </div>

      <div className="card span-12">
        <div className="section-title">Execution History</div>
        <table className="table">
          <thead><tr><th>Side</th><th>Entry</th><th>Exit</th><th>PnL $</th><th>PnL %</th></tr></thead>
          <tbody>
            {trades.slice(-10).reverse().map((t,i)=><tr key={i}>
              <td>{t.side}</td>
              <td className="mono">{fmt(t.entry)}</td>
              <td className="mono">{fmt(t.exit)}</td>
              <td className={`mono ${Number(t.pnl||0)>=0?'good':'bad'}`}>{fmt(t.pnl)}</td>
              <td className={`mono ${Number(t.pnl_pct||0)>=0?'good':'bad'}`}>{fmt(t.pnl_pct,'%')}</td>
            </tr>)}
          </tbody>
        </table>
      </div>

      <div className="card span-7">
        <div className="section-title">Volatility Target Allocation</div>
        <div className="section-sub">확정 4시간봉 기준 BTC 60% / ETH 30% / SOL 10% 기반 목표 비중이며, 신호·실현 변동성에 따라 현금 비중이 자동 조정된다.</div>
        <table className="table">
          <thead><tr><th>Asset</th><th>Target Weight</th><th>Signal</th><th>Volatility</th></tr></thead>
          <tbody>{Object.entries(targets).map(([symbol,weight])=>{
            const signal=decision?.signals?.[symbol]||{}
            return <tr key={symbol}>
              <td>{symbol}</td>
              <td className="mono">{fmt(Number(weight)*100,'%')}</td>
              <td className={signal.active?'good':'warn'}>{signal.active?'LONG':'CASH'}</td>
              <td className="mono">{fmt(Number(signal.realized_volatility||0)*100,'%')}</td>
            </tr>
          })}</tbody>
        </table>
        <div className="chip" style={{marginTop:12}}>Cash · {fmt(Number(decision.cash_weight||0)*100,'%')}</div>
      </div>

      <div className="card span-5">
        <div className="section-title">Enforced Risk Status</div>
        <div className="metric-label">Drawdown</div>
        <div className="metric-value mono" style={{fontSize:26}}>{fmt(Number(riskStatus.drawdown_pct||0)*100,'%')}</div>
        <div className="metric-label" style={{marginTop:12}}>Pending Orders</div>
        <div className="metric-value mono" style={{fontSize:26}}>{riskStatus.pending_count||0}</div>
        <div className="section-sub">{(riskStatus.rejected||[]).join(', ')||'현재 데이터·손실·스프레드 차단 사유 없음'}</div>
        <div className="metric-label" style={{marginTop:16}}>Market Regime</div>
        <div className="metric-value" style={{fontSize:22}}>{(marketRegime.direction||'unknown').toUpperCase()} / {(marketRegime.volatility||'unknown').toUpperCase()}</div>
        <div className="metric-note">노출 배수 {fmt(Number(marketRegime.exposure_multiplier||0)*100,'%')} · {(marketRegime.reasons||[]).join(', ')||'감축 사유 없음'}</div>
      </div>

      <div className="card span-12">
        <div className="section-title">Order Event Log</div>
        <table className="table">
          <thead><tr><th>Status</th><th>Symbol</th><th>Side</th><th>Target</th><th>Reason</th></tr></thead>
          <tbody>{orderEvents.slice(-20).reverse().map((event,index)=><tr key={`${event.order_id||index}-${event.status}`}>
            <td>{event.status||'-'}</td><td>{event.symbol||'-'}</td><td>{event.side||'-'}</td>
            <td className="mono">{fmt(Number(event.target_weight||0)*100,'%')}</td>
            <td>{(event.risk?.reasons||[]).join(', ')||'-'}</td>
          </tr>)}</tbody>
        </table>
      </div>

      <div className="card span-12">
        <div className="section-title">Paper Note</div>
        <div className="section-sub">{note || '실행 중인 paper session의 상태 메모가 여기에 표시된다.'}</div>
      </div>
    </div>
  </>)
}
