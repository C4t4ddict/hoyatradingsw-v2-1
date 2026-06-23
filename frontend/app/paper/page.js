'use client'
import { useEffect, useMemo, useState } from 'react'

const BASE = 'http://127.0.0.1:8010'
const SYMBOLS = ['BTC/USDT:USDT','ETH/USDT:USDT','XRP/USDT:USDT','SOL/USDT:USDT','DOGE/USDT:USDT','BNB/USDT:USDT','ADA/USDT:USDT','AVAX/USDT:USDT','LINK/USDT:USDT','SUI/USDT:USDT']

function fmt(n, suffix='') { return `${Number(n || 0).toFixed(2)}${suffix}` }

export default function PaperPage(){
  const [data,setData]=useState(null)
  const [loading,setLoading]=useState(false)
  const [symbol,setSymbol]=useState('XRP/USDT:USDT')
  const [leverage,setLeverage]=useState(10)
  const [initialUsdt,setInitialUsdt]=useState(1000)

  const load=async()=>{ const r=await fetch(`${BASE}/api/paper`,{cache:'no-store'}); setData(await r.json()) }
  useEffect(()=>{ load() },[])

  const call=async(path, body=null)=>{
    setLoading(true)
    await fetch(`${BASE}${path}`,{method:'POST', headers:{'Content-Type':'application/json'}, body: body ? JSON.stringify(body) : null})
    await load()
    setLoading(false)
  }

  const startPaper=async()=>{
    await call('/api/paper/start', {
      market_type:'futures',
      symbol,
      timeframe:'15m',
      strategy:'ensemble_regime',
      initial_usdt:Number(initialUsdt),
      position_mode:'both',
      leverage:Number(leverage),
      mode:'ml_signal',
      live_refresh_sec:10
    })
  }

  const m=data?.metrics||{}
  const trades=(data?.result?.trades)||[]
  const d=data?.ml_signal?.decision||{}
  const s=data?.ml_signal?.scores||{}
  const note=data?.paper_note||''
  const latestTrade = trades.length ? trades[trades.length - 1] : null
  const runningState = data?.running ? 'RUN' : (data?.paused ? 'PAUSE':'STOP')
  const latestTradePnlClass = Number(latestTrade?.pnl || 0) >= 0 ? 'good' : 'bad'

  const positionSummary = useMemo(() => ({
    side: latestTrade?.side || d.bias || '-',
    entry: fmt(latestTrade?.entry),
    exit: fmt(latestTrade?.exit),
    pnl: fmt(latestTrade?.pnl),
    pnlPct: fmt(latestTrade?.pnl_pct, '%'),
  }), [latestTrade, d.bias])

  return (<>
    <div className="topbar">
      <div>
        <div className="topbar-title">Paper Trading Operations</div>
        <div className="topbar-sub">심볼 / 레버리지 / 상태 변경이 즉시 반영되는 paper trading 운영 콘솔</div>
      </div>
      <div className={`chip ${runningState === 'RUN' ? 'good' : runningState === 'PAUSE' ? 'warn' : 'bad'}`}>{runningState}</div>
    </div>

    <h1 className="page-title">Paper Trading</h1>
    <p className="page-sub">ML signal 기반 가상 운용을 제어하고, 최근 체결/손익/알림 형식을 한 화면에서 확인하는 페이지</p>

    <div className="grid">
      <div className="card span-4 emphasis">
        <div className="metric-label">Current Session</div>
        <div className="metric-value">{runningState}</div>
        <div className="section-sub">현재 paper session 상태와 최신 운용 모드</div>
        <div style={{display:'flex', gap:8, flexWrap:'wrap'}}>
          <span className="chip">{data?.executed_strategy || 'strategy -'}</span>
          <span className="chip">{data?.executed_timeframe || 'tf -'}</span>
          <span className="chip warn">{data?.fallback_mode || '-'}</span>
        </div>
      </div>

      <div className="card span-4">
        <div className="metric-label">Virtual Balance</div>
        <div className="metric-value mono">${fmt(m.virtual_balance)}</div>
        <div className="metric-note">시작 잔액 대비 현재 가상 잔고</div>
      </div>

      <div className="card span-4">
        <div className="metric-label">Current Bias</div>
        <div className="metric-value">{(d.bias || 'neutral').toUpperCase()}</div>
        <div className="metric-note">live intel + ML assist 기준 현재 방향성</div>
      </div>

      <div className="card span-6">
        <div className="section-title">Config Panel</div>
        <div className="section-sub">변경사항은 즉시 반영되는 운영 제어 패널</div>
        <div className="mini-grid">
          <div>
            <div className="metric-label">Symbol</div>
            <input list="symbol-options" value={symbol} onChange={e=>setSymbol(e.target.value)} placeholder="심볼 검색" />
            <datalist id="symbol-options">{SYMBOLS.map(s=><option key={s} value={s} />)}</datalist>
          </div>
          <div>
            <div className="metric-label">Leverage</div>
            <input type="number" value={leverage} onChange={e=>setLeverage(e.target.value)} />
          </div>
          <div>
            <div className="metric-label">Starting Balance</div>
            <input type="number" value={initialUsdt} onChange={e=>setInitialUsdt(e.target.value)} />
          </div>
          <div>
            <div className="metric-label">Mode</div>
            <div className="chip good">ml_signal</div>
          </div>
        </div>
        <div className="button-row" style={{marginTop:16}}>
          <button onClick={startPaper} disabled={loading}>시작</button>
          <button onClick={()=>call('/api/paper/pause')} disabled={loading}>일시정지</button>
          <button onClick={()=>call('/api/paper/reset')} disabled={loading}>리셋</button>
          <button onClick={load} disabled={loading}>새로고침</button>
        </div>
      </div>

      <div className="card span-6">
        <div className="section-title">Current Position Snapshot</div>
        <div className="mini-grid">
          <div><div className="metric-label">Side</div><div className="metric-value" style={{fontSize:24}}>{positionSummary.side}</div></div>
          <div><div className="metric-label">Leverage</div><div className="metric-value mono" style={{fontSize:24}}>{fmt(leverage, 'x')}</div></div>
          <div><div className="metric-label">Entry</div><div className="metric-value mono" style={{fontSize:24}}>{positionSummary.entry}</div></div>
          <div><div className="metric-label">Exit / Current</div><div className="metric-value mono" style={{fontSize:24}}>{positionSummary.exit}</div></div>
          <div><div className="metric-label">PnL $</div><div className={`metric-value mono ${latestTradePnlClass}`} style={{fontSize:24}}>{positionSummary.pnl}</div></div>
          <div><div className="metric-label">PnL %</div><div className={`metric-value mono ${latestTradePnlClass}`} style={{fontSize:24}}>{positionSummary.pnlPct}</div></div>
        </div>
      </div>

      <div className="card span-4">
        <div className="section-title">ML Signal Stack</div>
        <div className="metric-label">Long Score</div><div className="metric-value good mono">{fmt(s.long_score)}</div>
        <div className="metric-label" style={{marginTop:12}}>Short Score</div><div className="metric-value bad mono">{fmt(s.short_score)}</div>
      </div>

      <div className="card span-8">
        <div className="section-title">Telegram Alert Preview</div>
        <div className="section-sub">최근 체결 결과를 알림 메시지 형식으로 미리 보는 카드</div>
        <div className="card soft">
          <div style={{fontWeight:800, marginBottom:10}}>📡 Paper Trade Alert</div>
          <div className="metric-note mono">시작 잔액: ${fmt(initialUsdt)}</div>
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

      <div className="card span-12">
        <div className="section-title">Paper Note</div>
        <div className="section-sub">{note || '실행 중인 paper session의 상태 메모가 여기에 표시된다.'}</div>
      </div>
    </div>
  </>)
}
