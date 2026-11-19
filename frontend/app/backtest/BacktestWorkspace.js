'use client'

import { useRef, useState } from 'react'
import { postJson } from '../../lib/api'
import { koPosition } from '../../lib/ko'
import { number, percent, timeLabel } from '../../lib/trading-chart.mjs'
import { DetailTable, MetricStrip, Tabs } from '../terminal/Terminal'
import ResultChart from './ResultChart'
import './backtest.css'

const STRATEGIES = {
  ema_cross: 'EMA 교차', rsi_reversion: 'RSI 평균회귀', breakout_20: '20봉 돌파',
  trend_continuation_system: '추세 지속', volatility_breakout_atr: '변동성 돌파',
}
const REASONS = { signal: '신호 종료', sl: '손절', tp: '목표가', liquidation: '강제 청산', end_of_test: '기간 종료' }
const MARKETS = { spot: '현물', futures: 'USDT 무기한 선물' }
const DIRECTIONS = { long: '매수', short: '매도', both: '양방향' }
const TIMEFRAMES = { '15m': '15분', '1h': '1시간', '4h': '4시간' }

function Choices({ label, name, values, form, update, disabled }) {
  return <label>{label}<select disabled={disabled} value={form[name]} onChange={event => update(name, event.target.value)}>
    {Object.entries(values).map(([value, text]) => <option key={value} value={value}>{text}</option>)}
  </select></label>
}

function Facts({ items }) {
  return <dl className="backtest-facts">{items.map(([label, value]) =>
    <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
}

function TradeResults({ trades }) {
  return <DetailTable columns={['방향', '진입 시각 (KST)', '진입가', '청산 시각 (KST)', '청산가', '순손익 (USDT)', '비용 (USDT)', '종료 사유']}
    empty="이 조건에서 발생한 거래가 없습니다."
    rows={[...trades].reverse().map((trade, index) => ({ id: index, cells: [
      koPosition(trade.side), timeLabel(trade.entry_ts), number(trade.entry), timeLabel(trade.exit_ts), number(trade.exit),
      <span key="pnl" className={trade.pnl >= 0 ? 'good' : 'bad'}>{number(trade.pnl)}</span>,
      number((trade.fees ?? 0) + (trade.funding_fee ?? 0)), REASONS[trade.reason] || trade.reason,
    ] }))} />
}

export default function BacktestWorkspace({ today, start }) {
  const [form, setForm] = useState({
    asset: 'BTC', market_type: 'spot', timeframe: '4h', start_date: start, end_date: today,
    strategy: 'ema_cross', position_mode: 'long', initial_usdt: 1000, fee_percent: 0.05,
    slippage_percent: 0.05, leverage: 1,
  })
  const [result, setResult] = useState(null)
  const [runNumber, setRunNumber] = useState(0)
  const [submitted, setSubmitted] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const locked = useRef(false)

  function update(key, value) {
    setForm(current => ({
      ...current, [key]: value,
      ...(key === 'market_type' && value === 'spot' ? { position_mode: 'long', leverage: 1 } : {}),
    }))
  }

  async function run(event) {
    event.preventDefault()
    if (locked.current) return
    locked.current = true
    setLoading(true)
    setError('')
    try {
      const { fee_percent, slippage_percent, ...request } = form
      const data = await postJson('/api/backtests/run', {
        ...request, initial_usdt: Number(request.initial_usdt), leverage: Number(request.leverage),
        fee_pct: Number(fee_percent) / 100, slippage_pct: Number(slippage_percent) / 100,
      })
      setResult(data)
      setSubmitted(form)
      setRunNumber(count => count + 1)
    } catch (exception) {
      setError(exception.message)
    } finally {
      locked.current = false
      setLoading(false)
    }
  }

  const changed = submitted && Object.keys(form).some(key => String(form[key]) !== String(submitted[key]))
  const metrics = result?.metrics
  const source = result?.source
  const request = result?.request
  const field = (label, key, attributes) => <label>{label}<input required {...attributes}
    value={form[key]} onChange={event => update(key, event.target.value)} /></label>
  const select = (label, name, values, disabled) => <Choices {...{ label, name, values, form, update, disabled }} />
  const empty = <p className="terminal-empty">백테스트 실행 후 확인할 수 있습니다.</p>

  return <div className="terminal backtest-terminal">
    <header className="terminal-header">
      <div><p className="terminal-eyebrow">HOYA / 전략 검증</p><h1>전략 백테스트</h1></div>
      <div className="terminal-header-actions">
        {loading && <span className="terminal-tag warn" role="status">검증 중</span>}
        {changed && <span className="terminal-tag warn">입력 변경 · 마지막 성공 결과 표시 중</span>}
        <span className="terminal-tag">Binance 공개 시세</span>
      </div>
    </header>
    <MetricStrip items={[
      ['전략 수익률', percent(metrics?.return_pct), metrics && (metrics.return_pct >= 0 ? 'good' : 'bad')],
      ['시장 대비 초과 성과 (%p)', number(metrics?.excess_return_pct), metrics && (metrics.excess_return_pct >= 0 ? 'good' : 'bad')],
      ['최대 낙폭', percent(metrics?.max_drawdown_pct)],
      ['연환산 Sharpe', number(metrics?.sharpe)],
      ['총 거래', number(metrics?.total_trades, 0)],
    ]} />
    <div className="terminal-workspace">
      <ResultChart key={runNumber} result={result} loading={loading} />
      <form className="terminal-panel terminal-context backtest-settings" onSubmit={run}>
        <div className="terminal-panel-heading"><h2>검증 조건</h2><span className="terminal-tag">KST</span></div>
        <fieldset disabled={loading} className="backtest-inputs">
          <legend className="backtest-visually-hidden">전략 테스트 입력</legend>
          {select('투자 대상', 'asset', { BTC: 'BTC', ETH: 'ETH', SOL: 'SOL' })}
          {select('시장', 'market_type', MARKETS)}
          {select('시간 단위', 'timeframe', TIMEFRAMES)}
          {select('전략', 'strategy', STRATEGIES)}
          {field('시작일', 'start_date', { type: 'date', max: form.end_date })}
          {field('종료일', 'end_date', { type: 'date', min: form.start_date, max: today })}
          {field('시작 자산 (USDT)', 'initial_usdt', { type: 'number', min: 100, max: 1_000_000, step: 'any' })}
          {select('방향', 'position_mode', DIRECTIONS, form.market_type === 'spot')}
          {field('수수료 (%)', 'fee_percent', { type: 'number', min: 0, max: 2, step: 'any' })}
          {field('슬리피지 (%)', 'slippage_percent', { type: 'number', min: 0, max: 2, step: 'any' })}
          {form.market_type === 'futures' && field('레버리지 (배)', 'leverage', { type: 'number', min: 1, max: 5, step: 'any' })}
        </fieldset>
        <button type="submit" className="backtest-run" disabled={loading}>{loading ? '공개 시세로 검증 중…' : '백테스트 실행'}</button>
        {error && <p className="backtest-feedback bad" role="alert">{error}</p>}
        {request && <p className="backtest-feedback" role="status">
          마지막 성공 · {STRATEGIES[request.strategy]} · {MARKETS[request.market_type]} · {DIRECTIONS[request.position_mode]} {request.leverage}배
          <br />{request.start_date} ~ {request.end_date}
        </p>}
      </form>
    </div>
    <Tabs tabs={[
      ['거래 내역', result ? <TradeResults key="trades" trades={result.trades ?? []} /> : empty],
      ['성과 상세', metrics ? <Facts key="metrics" items={[
        ['최종 자산', number(metrics.final_usdt) + ' USDT'], ['매수 후 보유 수익률', percent(metrics.benchmark_return_pct)],
        ['승률', percent(metrics.win_rate)], ['Profit Factor', number(metrics.profit_factor)],
        ['강제 청산', number(metrics.liquidation_count, 0)], ['총 수수료', number(metrics.total_fees) + ' USDT'],
        ['펀딩 정산', number(metrics.total_funding) + ' USDT'], ['Sharpe 무위험 수익률 가정', '0%'],
      ]} /> : empty],
      ['데이터·비용', source ? <Facts key="source" items={[
        ['시세 출처', source.provider], ['완료 캔들', number(source.candle_count, 0)],
        ['첫 완료 봉 (KST)', timeLabel(source.first_candle_at, true)], ['마지막 완료 봉 (KST)', timeLabel(source.last_candle_at, true)],
        ['시작 자산', number(request.initial_usdt) + ' USDT'], ['펀딩 이벤트', number(source.funding_event_count, 0)],
        ['수수료', percent(source.fee_pct, 100)], ['슬리피지', percent(source.slippage_pct, 100)],
      ]} /> : empty],
    ]} />
  </div>
}
