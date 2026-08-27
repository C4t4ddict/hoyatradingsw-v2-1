'use client'

import { useState } from 'react'
import { postJson } from '../../lib/api'
import { koPosition } from '../../lib/ko'

const STRATEGIES = [
  ['ema_cross', 'EMA 교차'],
  ['rsi_reversion', 'RSI 평균회귀'],
  ['breakout_20', '20봉 돌파'],
  ['trend_continuation_system', '추세 지속'],
  ['volatility_breakout_atr', '변동성 돌파'],
]

const REASONS = { signal:'신호 종료', sl:'손절', tp:'목표가', liquidation:'강제 청산', end_of_test:'기간 종료' }

function isoDate(daysAgo=0){
  const value = new Date()
  value.setDate(value.getDate() - daysAgo)
  const year=value.getFullYear()
  const month=String(value.getMonth()+1).padStart(2,'0')
  const day=String(value.getDate()).padStart(2,'0')
  return `${year}-${month}-${day}`
}

function num(value, digits=2){
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed.toLocaleString('ko-KR',{minimumFractionDigits:digits,maximumFractionDigits:digits}) : '-'
}

function pct(value){ return `${num(value)}%` }

function EquityChart({rows=[]}){
  if(rows.length < 2) return <div className="chart-empty">표시할 자산 곡선이 없습니다.</div>
  const width=920, height=280, pad=24
  const values=rows.map(row=>Number(row.equity))
  const min=Math.min(...values), max=Math.max(...values)
  const range=Math.max(max-min,1)
  const points=values.map((value,index)=>{
    const x=pad+(index/(values.length-1))*(width-pad*2)
    const y=height-pad-((value-min)/range)*(height-pad*2)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  return <div className="chart-wrap">
    <svg className="equity-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="백테스트 자산 곡선">
      <defs><linearGradient id="equity-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#4edea3" stopOpacity=".32"/><stop offset="1" stopColor="#4edea3" stopOpacity="0"/></linearGradient></defs>
      <line x1={pad} x2={width-pad} y1={pad} y2={pad} className="chart-grid" />
      <line x1={pad} x2={width-pad} y1={height-pad} y2={height-pad} className="chart-grid" />
      <polygon points={`${pad},${height-pad} ${points} ${width-pad},${height-pad}`} fill="url(#equity-fill)" />
      <polyline points={points} fill="none" stroke="#4edea3" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
    <div className="chart-axis"><span>최저 ${num(min)}</span><span>최고 ${num(max)}</span></div>
  </div>
}

export default function BacktestPage(){
  const [form,setForm]=useState({
    asset:'BTC', market_type:'spot', timeframe:'4h', start_date:isoDate(180), end_date:isoDate(),
    strategy:'ema_cross', position_mode:'long', initial_usdt:1000, fee_pct:0.0005,
    slippage_pct:0.0005, leverage:1,
  })
  const [result,setResult]=useState(null)
  const [loading,setLoading]=useState(false)
  const [error,setError]=useState('')

  const update=(key,value)=>{
    const next={...form,[key]:value}
    if(key==='market_type' && value==='spot'){
      next.position_mode='long'; next.leverage=1
    }
    setForm(next)
  }

  const run=async(event)=>{
    event.preventDefault(); setLoading(true); setError('')
    try{
      const payload={...form,initial_usdt:Number(form.initial_usdt),fee_pct:Number(form.fee_pct),slippage_pct:Number(form.slippage_pct),leverage:Number(form.leverage)}
      setResult(await postJson('/api/backtests/run',payload))
    }catch(exc){ setError(exc.message); setResult(null) }
    finally{ setLoading(false) }
  }

  const metrics=result?.metrics
  const source=result?.source
  const trades=result?.trades||[]

  return <>
    <div className="topbar">
      <div><div className="topbar-title">전략 백테스트</div><div className="topbar-sub">공개 시세와 다음 봉 체결 기준으로 전략 성과를 검증합니다.</div></div>
      <span className="chip good">실계좌 미사용</span>
    </div>
    <h1 className="page-title">백테스트</h1>
    <p className="page-sub">기간·전략·비용 가정을 고정하고 절대 성과, 시장 대비 성과와 위험을 함께 확인합니다.</p>

    <div className="grid">
      <form className="card span-12" onSubmit={run}>
        <div className="section-title">검증 조건</div>
        <div className="section-sub">Binance 공개 OHLCV만 조회하며 주문이나 계정 API는 호출하지 않습니다.</div>
        <div className="form-grid">
          <label>투자 대상<select value={form.asset} onChange={e=>update('asset',e.target.value)}><option>BTC</option><option>ETH</option><option>SOL</option></select></label>
          <label>시장<select value={form.market_type} onChange={e=>update('market_type',e.target.value)}><option value="spot">현물</option><option value="futures">USDT 무기한 선물</option></select></label>
          <label>시간 단위<select value={form.timeframe} onChange={e=>update('timeframe',e.target.value)}><option value="15m">15분</option><option value="1h">1시간</option><option value="4h">4시간</option></select></label>
          <label>전략<select value={form.strategy} onChange={e=>update('strategy',e.target.value)}>{STRATEGIES.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
          <label>시작일<input type="date" value={form.start_date} max={form.end_date} onChange={e=>update('start_date',e.target.value)} /></label>
          <label>종료일<input type="date" value={form.end_date} max={isoDate()} onChange={e=>update('end_date',e.target.value)} /></label>
          <label>포지션 방향<select value={form.position_mode} disabled={form.market_type==='spot'} onChange={e=>update('position_mode',e.target.value)}><option value="long">매수</option><option value="short">매도</option><option value="both">양방향</option></select></label>
          <label>시작 자산 (USDT)<input type="number" min="100" max="1000000" step="100" value={form.initial_usdt} onChange={e=>update('initial_usdt',e.target.value)} /></label>
          <label>레버리지<input type="number" min="1" max="5" step="1" disabled={form.market_type==='spot'} value={form.leverage} onChange={e=>update('leverage',e.target.value)} /></label>
          <label>거래 수수료<input type="number" min="0" max="0.02" step="0.0001" value={form.fee_pct} onChange={e=>update('fee_pct',e.target.value)} /></label>
          <label>슬리피지<input type="number" min="0" max="0.02" step="0.0001" value={form.slippage_pct} onChange={e=>update('slippage_pct',e.target.value)} /></label>
        </div>
        <div className="button-row" style={{marginTop:18}}><button type="submit" disabled={loading}>{loading?'공개 시세 수집·검증 중…':'백테스트 실행'}</button></div>
        {error&&<div className="inline-error">{error}</div>}
      </form>

      {!metrics&&<div className="card span-12 empty-state"><div className="section-title">아직 실행 결과가 없습니다.</div><div className="section-sub">기본값은 최근 180일 BTC 현물 4시간봉 EMA 교차 전략입니다. 실행하면 성과와 위험 지표가 여기에 표시됩니다.</div></div>}

      {metrics&&<>
        <div className="card span-3 emphasis"><div className="metric-label">전략 수익률</div><div className={`metric-value ${metrics.return_pct>=0?'good':'bad'}`}>{pct(metrics.return_pct)}</div><div className="metric-note">최종 ${num(metrics.final_usdt)} USDT</div></div>
        <div className="card span-3"><div className="metric-label">시장 대비 초과 성과</div><div className={`metric-value ${metrics.excess_return_pct>=0?'good':'bad'}`}>{pct(metrics.excess_return_pct)}</div><div className="metric-note">동일 비용 Buy & Hold {pct(metrics.benchmark_return_pct)}</div></div>
        <div className="card span-3"><div className="metric-label">최대 낙폭</div><div className={`metric-value ${metrics.max_drawdown_pct<=15?'good':'bad'}`}>{pct(metrics.max_drawdown_pct)}</div><div className="metric-note">낮을수록 손실 방어가 우수</div></div>
        <div className="card span-3"><div className="metric-label">Sharpe</div><div className="metric-value">{num(metrics.sharpe)}</div><div className="metric-note">연환산 무위험 수익률 0% 가정</div></div>

        <div className="card span-8">
          <div className="split"><div><div className="section-title">자산 곡선</div><div className="section-sub">다음 봉 시가 체결과 수수료·슬리피지를 반영한 평가 자산</div></div><span className="chip">{result.request.start_date} – {result.request.end_date}</span></div>
          <EquityChart rows={result.equity_curve}/>
        </div>
        <div className="card span-4">
          <div className="section-title">거래 품질</div>
          <div className="backtest-stat"><span>총 거래</span><strong>{metrics.total_trades}건</strong></div>
          <div className="backtest-stat"><span>승률</span><strong>{pct(metrics.win_rate)}</strong></div>
          <div className="backtest-stat"><span>Profit Factor</span><strong>{num(metrics.profit_factor)}</strong></div>
          <div className="backtest-stat"><span>강제 청산</span><strong className={metrics.liquidation_count?'bad':'good'}>{metrics.liquidation_count}건</strong></div>
          <div className="backtest-stat"><span>총 수수료</span><strong>{num(metrics.total_fees)} USDT</strong></div>
          <div className="backtest-stat"><span>펀딩 정산</span><strong>{num(metrics.total_funding)} USDT</strong></div>
        </div>

        <div className="card span-12">
          <div className="split"><div><div className="section-title">데이터 출처와 가정</div><div className="section-sub">결과 해석에 필요한 데이터 범위와 비용 모델</div></div><span className="chip good">{source.authenticated?'인증 사용':'공개 데이터'}</span></div>
          <div className="source-grid">
            <div><span>출처</span><strong>{source.provider}</strong></div><div><span>완료 캔들</span><strong>{source.candle_count.toLocaleString('ko-KR')}개</strong></div>
            <div><span>첫 캔들</span><strong>{new Date(source.first_candle_at).toLocaleString('ko-KR')}</strong></div><div><span>마지막 캔들</span><strong>{new Date(source.last_candle_at).toLocaleString('ko-KR')}</strong></div>
            <div><span>수수료</span><strong>{pct(source.fee_pct*100)}</strong></div><div><span>슬리피지</span><strong>{pct(source.slippage_pct*100)}</strong></div>
          </div>
        </div>

        <div className="card span-12">
          <div className="section-title">최근 거래</div><div className="section-sub">최대 100건을 최신 거래 기준으로 표시합니다.</div>
          <div className="table-scroll"><table className="table"><thead><tr><th>방향</th><th>진입</th><th>청산</th><th>손익</th><th>비용</th><th>종료 사유</th></tr></thead><tbody>
            {trades.slice().reverse().map((trade,index)=><tr key={`${trade.entry_ts}-${index}`}><td>{koPosition(trade.side)}</td><td><div className="mono">${num(trade.entry)}</div><div className="metric-note">{new Date(trade.entry_ts).toLocaleString('ko-KR')}</div></td><td><div className="mono">${num(trade.exit)}</div><div className="metric-note">{new Date(trade.exit_ts).toLocaleString('ko-KR')}</div></td><td className={`mono ${trade.pnl>=0?'good':'bad'}`}>${num(trade.pnl)}</td><td className="mono">${num(Number(trade.fees||0)+Number(trade.funding_fee||0))}</td><td>{REASONS[trade.reason]||trade.reason}</td></tr>)}
            {!trades.length&&<tr><td colSpan="6" className="muted">조건에 맞는 거래가 발생하지 않았습니다.</td></tr>}
          </tbody></table></div>
        </div>
      </>}
    </div>
  </>
}
