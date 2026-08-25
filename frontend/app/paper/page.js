'use client'
import { useEffect, useMemo, useState } from 'react'
import { koBias, koFallback, koPosition, koStatus, koStrategy } from '../../lib/ko'

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
  const runningLabel = data?.running ? '운용 중' : (data?.paused ? '일시정지':'중지')
  const latestTradePnlClass = Number(latestTrade?.pnl || 0) >= 0 ? 'good' : 'bad'

  const positionSummary = useMemo(() => ({
    side: koPosition(latestTrade?.side || 'cash'),
    entry: fmt(latestTrade?.entry),
    exit: fmt(latestTrade?.exit),
    pnl: fmt(latestTrade?.pnl),
    pnlPct: fmt(latestTrade?.pnl_pct, '%'),
  }), [latestTrade])

  return (<>
    <div className="topbar">
      <div>
        <div className="topbar-title">모의투자 운영</div>
        <div className="topbar-sub">검증된 고정 투자 대상과 변동성 목표, 세션 상태를 관리합니다.</div>
      </div>
      <div className={`chip ${runningState === 'RUN' ? 'good' : runningState === 'PAUSE' ? 'warn' : 'bad'}`}>{runningLabel}</div>
    </div>

    <h1 className="page-title">모의투자</h1>
    <p className="page-sub">확정 4시간봉 기반 BTC·ETH·SOL 매수·현금 변동성 목표 전략을 제어하고 감시합니다.</p>

    <div className="grid">
      <div className="card span-4 emphasis">
        <div className="metric-label">현재 세션</div>
        <div className="metric-value">{runningLabel}</div>
        <div className="section-sub">현재 모의투자 세션 상태와 최신 운용 모드</div>
        <div style={{display:'flex', gap:8, flexWrap:'wrap'}}>
          <span className="chip">{koStrategy(data?.executed_strategy || cfg.strategy)}</span>
          <span className="chip">{data?.executed_timeframe || cfg.timeframe || '-'}</span>
          <span className="chip warn">{koFallback(data?.fallback_mode)}</span>
        </div>
      </div>

      <div className="card span-4">
        <div className="metric-label">가상 잔액</div>
        <div className="metric-value mono">${fmt(m.virtual_balance)}</div>
        <div className="metric-note">시작 잔액 대비 현재 가상 잔고</div>
      </div>

      <div className="card span-4">
        <div className="metric-label">참고 방향</div>
        <div className="metric-value">{koBias(d.bias)}</div>
        <div className="metric-note">운영 참고용이며 변동성 목표 주문 방향을 직접 결정하지 않음</div>
      </div>

      <div className="card span-6">
        <div className="section-title">운용 설정</div>
        <div className="section-sub">실행 엔진과 동일한 BTC·ETH·SOL · 현물 · 4시간 · 매수/현금 · 1배 설정만 제공합니다.</div>
        <div className="mini-grid">
          <div>
            <div className="metric-label">투자 대상</div>
            <div className="metric-note mono">BTC / ETH / SOL</div>
          </div>
          <div>
            <div className="metric-label">레버리지 / 방향</div>
            <div className="metric-note mono">1배 / 매수·현금</div>
          </div>
          <div>
            <div className="metric-label">시작 잔액</div>
            <input type="number" value={initialUsdt} onChange={e=>setInitialUsdt(e.target.value)} />
          </div>
          <div>
            <div className="metric-label">목표 변동성 %</div>
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
        <div className="section-title">현재 포지션 현황</div>
        <div className="mini-grid">
          <div><div className="metric-label">방향</div><div className="metric-value" style={{fontSize:24}}>{positionSummary.side}</div></div>
          <div><div className="metric-label">레버리지</div><div className="metric-value mono" style={{fontSize:24}}>1.00배</div></div>
          <div><div className="metric-label">진입가</div><div className="metric-value mono" style={{fontSize:24}}>{positionSummary.entry}</div></div>
          <div><div className="metric-label">청산가 / 현재가</div><div className="metric-value mono" style={{fontSize:24}}>{positionSummary.exit}</div></div>
          <div><div className="metric-label">손익 $</div><div className={`metric-value mono ${latestTradePnlClass}`} style={{fontSize:24}}>{positionSummary.pnl}</div></div>
          <div><div className="metric-label">손익 %</div><div className={`metric-value mono ${latestTradePnlClass}`} style={{fontSize:24}}>{positionSummary.pnlPct}</div></div>
        </div>
      </div>

      <div className="card span-4">
        <div className="section-title">참고 신호 점수</div>
        <div className="metric-label">상승 점수</div><div className="metric-value good mono">{fmt(s.long_score)}</div>
        <div className="metric-label" style={{marginTop:12}}>하락 점수</div><div className="metric-value bad mono">{fmt(s.short_score)}</div>
      </div>

      <div className="card span-8">
        <div className="section-title">텔레그램 알림 미리보기</div>
        <div className="section-sub">최근 체결 결과를 알림 메시지 형식으로 미리 보는 카드</div>
        <div className="card soft">
          <div style={{fontWeight:800, marginBottom:10}}>📡 모의투자 체결 알림</div>
          <div className="metric-note mono">시작 잔액: ${fmt(m.starting_balance ?? initialUsdt)}</div>
          <div className="metric-note mono">진입/청산: {positionSummary.entry} → {positionSummary.exit}</div>
          <div className={`metric-note mono ${latestTradePnlClass}`}>손익 $: {positionSummary.pnl}</div>
          <div className={`metric-note mono ${latestTradePnlClass}`}>손익 %: {positionSummary.pnlPct}</div>
          <div className="metric-note mono">종료 잔액: ${fmt(m.virtual_balance)}</div>
        </div>
      </div>

      <div className="card span-12">
        <div className="section-title">체결 내역</div>
        <table className="table">
          <thead><tr><th>방향</th><th>진입가</th><th>청산가</th><th>손익 $</th><th>손익 %</th></tr></thead>
          <tbody>
            {trades.slice(-10).reverse().map((t,i)=><tr key={i}>
              <td>{koPosition(t.side)}</td>
              <td className="mono">{fmt(t.entry)}</td>
              <td className="mono">{fmt(t.exit)}</td>
              <td className={`mono ${Number(t.pnl||0)>=0?'good':'bad'}`}>{fmt(t.pnl)}</td>
              <td className={`mono ${Number(t.pnl_pct||0)>=0?'good':'bad'}`}>{fmt(t.pnl_pct,'%')}</td>
            </tr>)}
          </tbody>
        </table>
      </div>

      <div className="card span-7">
        <div className="section-title">변동성 목표 자산 배분</div>
        <div className="section-sub">확정 4시간봉 기준 BTC 60% / ETH 30% / SOL 10% 기반 목표 비중이며, 신호·실현 변동성에 따라 현금 비중이 자동 조정된다.</div>
        <table className="table">
          <thead><tr><th>자산</th><th>목표 비중</th><th>신호</th><th>변동성</th></tr></thead>
          <tbody>{Object.entries(targets).map(([symbol,weight])=>{
            const signal=decision?.signals?.[symbol]||{}
            return <tr key={symbol}>
              <td>{symbol}</td>
              <td className="mono">{fmt(Number(weight)*100,'%')}</td>
              <td className={signal.active?'good':'warn'}>{signal.active?'매수':'현금'}</td>
              <td className="mono">{fmt(Number(signal.realized_volatility||0)*100,'%')}</td>
            </tr>
          })}</tbody>
        </table>
        <div className="chip" style={{marginTop:12}}>현금 · {fmt(Number(decision.cash_weight||0)*100,'%')}</div>
      </div>

      <div className="card span-5">
        <div className="section-title">강제 위험 관리 상태</div>
        <div className="metric-label">낙폭</div>
        <div className="metric-value mono" style={{fontSize:26}}>{fmt(Number(riskStatus.drawdown_pct||0)*100,'%')}</div>
        <div className="metric-label" style={{marginTop:12}}>대기 주문</div>
        <div className="metric-value mono" style={{fontSize:26}}>{riskStatus.pending_count||0}</div>
        <div className="section-sub">{(riskStatus.rejected||[]).join(', ')||'현재 데이터·손실·스프레드 차단 사유 없음'}</div>
        <div className="metric-label" style={{marginTop:16}}>시장 국면</div>
        <div className="metric-value" style={{fontSize:22}}>{koBias(marketRegime.direction||'neutral')} / {marketRegime.volatility==='high'?'고변동':marketRegime.volatility==='low'?'저변동':marketRegime.volatility==='normal'?'보통':'미확인'}</div>
        <div className="metric-note">노출 배수 {fmt(Number(marketRegime.exposure_multiplier||0)*100,'%')} · {(marketRegime.reasons||[]).join(', ')||'감축 사유 없음'}</div>
      </div>

      <div className="card span-12">
        <div className="section-title">주문 이벤트 기록</div>
        <table className="table">
          <thead><tr><th>상태</th><th>종목</th><th>방향</th><th>목표</th><th>사유</th></tr></thead>
          <tbody>{orderEvents.slice(-20).reverse().map((event,index)=><tr key={`${event.order_id||index}-${event.status}`}>
            <td>{koStatus(event.status)}</td><td>{event.symbol||'-'}</td><td>{koPosition(event.side)}</td>
            <td className="mono">{fmt(Number(event.target_weight||0)*100,'%')}</td>
            <td>{(event.risk?.reasons||[]).join(', ')||'-'}</td>
          </tr>)}</tbody>
        </table>
      </div>

      <div className="card span-12">
        <div className="section-title">모의투자 메모</div>
        <div className="section-sub">{note || '실행 중인 모의투자 세션의 상태 메모가 여기에 표시됩니다.'}</div>
      </div>
    </div>
  </>)
}
