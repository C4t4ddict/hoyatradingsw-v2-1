'use client'

import { useRef, useState } from 'react'
import Link from 'next/link'
import { fetchJson, postJson } from '../../lib/api'
import { koBias, koFallback, koPosition, koStatus, koStrategy } from '../../lib/ko'
import { number, percent, timeLabel } from '../../lib/trading-chart.mjs'
import CandleChart from '../terminal/CandleChart'
import { DetailTable, MetricStrip, SignalDetails, SignalResults, Tabs } from '../terminal/Terminal'
import './paper.css'

const NOTES = {
  'fresh paper session': '새 모의투자 세션이 시작되었습니다.',
  'confirmed 4h close signal; pending orders execute at next 4h open': '확정 4시간봉 종가로 판단하고 다음 4시간봉 시가에 대기 주문을 체결합니다.',
}
const REASONS = {
  daily_loss_limit: '일일 손실 한도', drawdown_buy_block: '낙폭 한도에 따른 매수 차단',
  stale_market_data: '시세 갱신 지연', kill_switch: '긴급 중지',
}
const reasonLabel = reason => REASONS[reason] || reason

function PositionTable({ portfolio }) {
  return <>
    {portfolio && <div className="terminal-summary">가상 현금 · {number(portfolio.cash)} USDT</div>}
    <DetailTable columns={['보유 종목', '수량', '평균 취득가 (USDT)']}
      empty={portfolio ? '현재 보유 종목이 없습니다.' : '엔진의 보유 현황을 확인할 수 없습니다.'}
      rows={(portfolio?.positions ?? []).map(row => ({ id: row.symbol,
        cells: [row.symbol, number(row.units, 8), number(row.average_cost)] }))} />
  </>
}

function FillTable({ fills }) {
  return <DetailTable columns={['실행 시각 (KST)', '종목', '방향', '체결가', '수량', '수수료 (USDT)', '실현 손익 (USDT)']}
    empty="세션에 기록된 체결이 없습니다."
    rows={fills.slice(-30).reverse().map((fill, index) => ({ id: fill.order_id || index, cells: [
      timeLabel(fill.execution_ms), fill.symbol || '—', koPosition(fill.side),
      number(fill.price), number(fill.units, 8), number(fill.fee), number(fill.realized_pnl ?? fill.pnl),
    ] }))} />
}

function OrderTable({ orders }) {
  return <DetailTable columns={['상태', '종목', '방향', '목표 비중', '사유']}
    empty="기록된 주문 이벤트가 없습니다."
    rows={orders.slice(-30).reverse().map((order, index) => ({ id: index, cells: [
      koStatus(order.status), order.symbol || '—', koPosition(order.side), percent(order.target_weight, 100),
      (order.risk?.reasons || []).map(reasonLabel).join(', ') || '—',
    ] }))} />
}

function StrategyDetails({ paper }) {
  const decision = paper?.strategy_decision
  const regime = paper?.market_regime
  const risk = paper?.risk_status
  const volatility = { high: '고변동', low: '저변동', normal: '보통' }[regime?.volatility]
  return <div className="paper-details">
    <div className="terminal-summary">
      <span>현금 목표 {percent(decision?.cash_weight, 100)}</span>
      <span>시장 국면 {regime?.direction ? koBias(regime.direction) : '—'} / {volatility || '—'}</span>
      <span>노출 배수 {percent(regime?.exposure_multiplier, 100)}</span>
      <span>시세 품질 {risk?.data_quality ? risk.data_quality.ok ? '정상' : '검증 실패' : '미확인'}</span>
    </div>
    <DetailTable columns={['종목', '목표 비중', '신호', '실현 변동성']}
      empty="아직 산출된 목표 비중이 없습니다."
      rows={Object.entries(decision?.target_weights ?? {}).map(([symbol, weight]) => {
        const signal = decision.signals?.[symbol]
        return { id: symbol, cells: [symbol, percent(weight, 100),
          signal ? signal.active ? '매수' : '현금' : '—', percent(signal?.realized_volatility, 100)] }
      })} />
    <div className="terminal-summary">
      {(risk?.rejected ?? []).map(reasonLabel).join(', ') || '기록된 주문 차단 사유 없음'}
      {(risk?.data_quality?.errors ?? []).map(reasonLabel).join(', ')}
      {(regime?.reasons ?? []).map(reasonLabel).join(', ')}
    </div>
  </div>
}

function SessionNotes({ paper, latest }) {
  return <div className="paper-notes">
    <h2>텔레그램 알림 미리보기</h2>
    {latest ? <p>{latest.symbol || '—'} {koPosition(latest.side)} · 체결가 {number(latest.price ?? latest.exit)} USDT
      {' · '}실현 손익 {number(latest.realized_pnl ?? latest.pnl)} USDT · 가상 자산 {number(paper?.metrics?.virtual_balance)} USDT</p>
      : <p>알림으로 미리 볼 체결이 없습니다.</p>}
    <h2>세션 메모</h2>
    <p>{NOTES[paper?.paper_note] || paper?.paper_note || '등록된 메모가 없습니다.'}</p>
  </div>
}

export default function PaperWorkspace({ initialPaper, initialSignals }) {
  const [paper, setPaper] = useState(initialPaper)
  const [signals, setSignals] = useState(initialSignals)
  const [cash, setCash] = useState(initialPaper?.config?.initial_usdt ?? 1000)
  const [volatility, setVolatility] = useState((initialPaper?.config?.target_volatility ?? 0.2) * 100)
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState(null)
  const [resetOpen, setResetOpen] = useState(false)
  const [settingsToken, setSettingsToken] = useState('')
  const [refresh, setRefresh] = useState(0)
  const locked = useRef(false)

  const running = paper?.running && !paper?.paused
  const state = !paper ? '확인 불가' : running ? '운용 중' : paper.paused ? '일시정지' : '중지'
  const metrics = paper?.metrics
  const risk = paper?.risk_status
  const fills = paper?.result?.trades ?? []
  const markers = fills.filter(fill => fill.symbol && ['buy', 'sell'].includes(fill.side) && Number.isFinite(fill.execution_ms))
    .map(fill => ({ time: fill.execution_ms, symbol: fill.symbol, kind: fill.side,
      label: `${number(fill.price)} USDT · ${number(fill.units, 8)}개` }))
  const valid = cash !== '' && Number(cash) >= 100 && Number(cash) <= 1000000
    && volatility !== '' && Number(volatility) >= 1 && Number(volatility) <= 25

  async function perform(action) {
    if (locked.current || (action !== 'refresh' && !settingsToken)) return
    locked.current = true
    setBusy(true)
    setFeedback(null)
    let applied = false
    try {
      if (action !== 'refresh') {
        const body = ['start', 'config'].includes(action) ? {
          ...paper?.config, market_type: 'spot', symbol: 'BTC/ETH/SOL', leverage: 1,
          initial_usdt: Number(cash), target_volatility: Number(volatility) / 100,
          strategy: 'vol_target_momentum', mode: 'vol_target_momentum', timeframe: '4h', position_mode: 'long_cash',
        } : null
        await postJson(`/api/paper/${action}`, body, settingsToken)
        applied = true
        setResetOpen(false)
      }
      const [paperResult, runtimeResult] = await Promise.allSettled([fetchJson('/api/paper'), fetchJson('/api/runtime')])
      setSignals(runtimeResult.status === 'fulfilled' ? runtimeResult.value.signals : null)
      setRefresh(value => value + 1)
      if (paperResult.status === 'rejected') throw paperResult.reason
      const updated = paperResult.value
      setPaper(updated)
      if (updated.config) {
        setCash(updated.config.initial_usdt)
        setVolatility(updated.config.target_volatility * 100)
      }
      setFeedback({ text: action === 'refresh' ? '최신 상태를 확인했습니다.' : '요청이 반영되었습니다.' })
    } catch (error) {
      setFeedback({ error: true, text: applied ? '요청이 반영됐습니다. 상태 확인에 실패했습니다. 새로고침으로 다시 확인하세요.'
        : action === 'refresh' ? '최신 상태를 불러오지 못했습니다.' : `요청 실패 · ${error.message}` })
    } finally {
      locked.current = false
      setBusy(false)
    }
  }

  return <div className="terminal">
    <header className="terminal-header">
      <div><p className="terminal-eyebrow">HOYA / 운용</p><h1>모의투자 워크스페이스</h1></div>
      <div className="terminal-header-actions">
        <span className="terminal-tag warn">모의투자 모드</span>
        <Link className="terminal-link" href="/">대시보드 ↗</Link>
      </div>
    </header>
    <MetricStrip items={[
      ['세션 상태', state, running ? 'good' : paper?.paused ? 'warn' : undefined],
      ['가상 자산 · USDT', number(metrics?.virtual_balance)],
      ['누적 수익률', percent(metrics?.return_pct), metrics?.return_pct == null ? undefined : metrics.return_pct >= 0 ? 'good' : 'bad'],
      ['일일 손실 한도', percent(paper?.daily_loss_limit_pct, 100)],
      ['세션 갱신 (KST)', timeLabel(paper?.last_update)],
    ]} />
    <div className="terminal-workspace">
      <CandleChart mode="paper" markers={markers} refresh={refresh} />
      <aside className="terminal-panel terminal-context paper-control" aria-label="모의투자 운용 설정">
        <div className="terminal-panel-heading"><h2>운용 설정</h2><span className="terminal-tag">현물 · 1배</span></div>
        <p className="paper-muted">{koStrategy(paper?.executed_strategy || paper?.config?.strategy)} · 매수·현금</p>
        <div className="paper-inputs">
          <label>설정 토큰<input type="password" autoComplete="off" value={settingsToken}
            disabled={busy} onChange={event => setSettingsToken(event.target.value)} /></label>
          <label>시작 잔액 (USDT)<input type="number" min="100" max="1000000" step="any"
            value={cash} disabled={busy} onChange={event => setCash(event.target.value)} /></label>
          <label>목표 변동성 (%)
            <input type="number" min="1" max="25" step="any" value={volatility}
              disabled={busy} onChange={event => setVolatility(event.target.value)} />
          </label>
        </div>
        <div className="paper-actions">
          <button type="button" className="paper-primary" disabled={busy || !settingsToken || !valid || !paper || running} onClick={() => perform('start')}>시작</button>
          <button type="button" disabled={busy || !settingsToken || !valid || !paper} onClick={() => perform('config')}>설정 반영</button>
          <button type="button" disabled={busy || !settingsToken || !running} onClick={() => perform('pause')}>일시정지</button>
          <button type="button" disabled={busy} onClick={() => perform('refresh')}>{busy ? '처리 중…' : '새로고침'}</button>
        </div>
        <p className="paper-muted">설정 반영 시 새 세션이 시작됩니다.</p>
        {!valid && <p className="paper-muted warn" role="status">잔액 100–1,000,000 USDT · 목표 변동성 1–25%</p>}
        {feedback && <p className={feedback.error ? 'paper-muted bad' : 'paper-muted good'} role={feedback.error ? 'alert' : 'status'}>{feedback.text}</p>}
        {!paper && <p className="paper-muted warn" role="status">세션 상태를 불러오지 못했습니다. 새로고침으로 다시 확인하세요.</p>}
        <dl className="terminal-facts terminal-divider">
          <div><dt>현재 낙폭</dt><dd>{percent(risk?.drawdown_pct, 100)}</dd></div>
          <div><dt>대기 주문</dt><dd>{number(risk?.pending_count, 0)}</dd></div>
          <div><dt>대체 정책</dt><dd>{paper ? koFallback(paper.fallback_mode ?? undefined) : '—'}</dd></div>
        </dl>
        {resetOpen ? <div className="paper-reset">
          <p role="alert">현재 모의투자 세션을 초기화할까요?</p>
          <div className="paper-actions">
            <button type="button" disabled={busy} onClick={() => setResetOpen(false)}>취소</button>
            <button type="button" className="bad" disabled={busy || !settingsToken} onClick={() => perform('reset')}>초기화 확인</button>
          </div>
        </div> : <button type="button" className="paper-reset-link" disabled={busy || !settingsToken || !paper} onClick={() => setResetOpen(true)}>세션 초기화…</button>}
      </aside>
    </div>
    <Tabs tabs={[
      ['포지션', <PositionTable key="positions" portfolio={paper?.portfolio} />],
      ['체결 내역', <FillTable key="fills" fills={fills} />],
      ['주문 이벤트', <OrderTable key="orders" orders={paper?.order_events ?? []} />],
      ['전략·위험', <StrategyDetails key="strategy" paper={paper} />],
      ['신호 결과', <div key="signals" className="paper-signal-details">
        <SignalDetails signal={paper?.ml_signal} />
        <p className="terminal-summary">전체 시스템 관찰 결과 · 차트의 모의 체결 기록과 별도 집계</p>
        <SignalResults signals={signals} />
      </div>],
      ['알림·메모', <SessionNotes key="notes" paper={paper} latest={fills.at(-1)} />],
    ]} />
  </div>
}
