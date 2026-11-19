'use client'

import { useEffect, useRef, useState } from 'react'
import { number, percent, timeLabel } from '../../lib/trading-chart.mjs'

const MODES = { equity: '자산 곡선', drawdown: '낙폭' }
const STRATEGY_COLOR = '#4edea3'
const BENCHMARK_COLOR = '#8bb3ff'
const DRAWDOWN_COLOR = '#f28a90'
const AXIS = { left: 14, right: 78, top: 16, bottom: 28 }

function draw(canvas, rows, mode, selected) {
  const { width, height } = canvas.getBoundingClientRect()
  if (width <= AXIS.left + AXIS.right || height <= AXIS.top + AXIS.bottom) return
  const scale = window.devicePixelRatio || 1
  canvas.width = Math.round(width * scale)
  canvas.height = Math.round(height * scale)
  const context = canvas.getContext('2d')
  context.scale(scale, scale)
  const right = width - AXIS.right
  const bottom = height - AXIS.bottom
  const firstTime = rows[0].ts
  const timeSpan = Math.max(rows.at(-1).ts - firstTime, 1)
  const series = mode === 'equity'
    ? [['equity', STRATEGY_COLOR], ['benchmark_equity', BENCHMARK_COLOR]]
    : [['drawdown_pct', DRAWDOWN_COLOR]]
  const values = series.flatMap(([key]) => rows.map(row => row[key]).filter(Number.isFinite))
  if (!values.length) return
  const min = mode === 'drawdown' ? 0 : Math.min(...values)
  const max = Math.max(...values)
  const padding = Math.max((max - min) * 0.07, mode === 'drawdown' ? 0.2 : 1)
  const low = mode === 'drawdown' ? 0 : min - padding
  const high = max + padding
  const xAt = time => AXIS.left + (time - firstTime) / timeSpan * (right - AXIS.left)
  const yAt = value => {
    const ratio = (value - low) / (high - low)
    return mode === 'drawdown' ? AXIS.top + ratio * (bottom - AXIS.top) : bottom - ratio * (bottom - AXIS.top)
  }
  function line(x, y, endX, endY, color) {
    context.beginPath()
    context.strokeStyle = color
    context.moveTo(x, y)
    context.lineTo(endX, endY)
    context.stroke()
  }
  context.font = '11px system-ui'
  context.textBaseline = 'middle'
  context.fillStyle = '#a4b2c8'
  for (let level = 0; level <= 5; level++) {
    const value = low + (high - low) * level / 5
    const y = yAt(value)
    line(AXIS.left, y, right, y, '#273248')
    context.fillText(mode === 'drawdown' ? percent(value) : number(value, 0), right + 8, y)
  }
  const dateFormat = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', month: 'numeric', day: 'numeric' })
  const ticks = Math.max(1, Math.min(6, Math.floor((right - AXIS.left) / 86)))
  for (let i = 0; i <= ticks; i++) {
    const time = firstTime + timeSpan * i / ticks
    const x = xAt(time)
    line(x, AXIS.top, x, bottom, '#273248')
    const label = dateFormat.format(time)
    context.fillText(label, Math.max(AXIS.left, Math.min(right - context.measureText(label).width, x - 14)), bottom + 14)
  }
  for (const [key, color] of series) {
    context.beginPath()
    context.strokeStyle = color
    context.lineWidth = 1.7
    let joined = false
    for (const row of rows) {
      if (!Number.isFinite(row[key])) {
        joined = false
        continue
      }
      const x = xAt(row.ts)
      const y = yAt(row[key])
      if (joined) context.lineTo(x, y)
      else context.moveTo(x, y)
      joined = true
    }
    context.stroke()
  }
  if (selected != null) {
    const x = xAt(rows[selected].ts)
    context.lineWidth = 1
    context.setLineDash([4, 4])
    line(x, AXIS.top, x, bottom, '#abb8cd')
    context.setLineDash([])
  }
}

export default function ResultChart({ result, loading }) {
  const [mode, setMode] = useState('equity')
  const [index, setIndex] = useState(null)
  const canvasRef = useRef(null)
  const rows = result?.equity_curve
  const selected = index == null ? null : Math.min(index, (rows?.length ?? 1) - 1)
  const point = (selected == null ? rows?.at(-1) : rows?.[selected])
  const ready = (rows?.length ?? 0) > 1
  const hasDrawdown = rows?.some(row => Number.isFinite(row.drawdown_pct))
  const chartMode = hasDrawdown ? mode : 'equity'
  useEffect(() => {
    if (!ready) return
    const canvas = canvasRef.current
    const redraw = () => draw(canvas, rows, chartMode, selected)
    const observer = new ResizeObserver(redraw)
    observer.observe(canvas)
    redraw()
    return () => observer.disconnect()
  }, [ready, rows, chartMode, selected])

  function pick(event) {
    const bounds = event.currentTarget.getBoundingClientRect()
    const fraction = (event.clientX - bounds.left - AXIS.left) / (bounds.width - AXIS.left - AXIS.right)
    if (fraction < 0 || fraction > 1) return
    const target = rows[0].ts + (rows.at(-1).ts - rows[0].ts) * fraction
    const nearest = rows.reduce((best, row, i) =>
      Math.abs(row.ts - target) < Math.abs(rows[best].ts - target) ? i : best, 0)
    setIndex(nearest)
  }

  return <section className="terminal-panel terminal-chart" aria-label="백테스트 성과 차트">
    <div className="terminal-chart-toolbar">
      <div className="terminal-switch" role="group" aria-label="결과 차트 종류">
        {Object.entries(MODES).map(([value, label]) => <button key={value} type="button"
          disabled={value === 'drawdown' && !hasDrawdown} aria-pressed={chartMode === value} onClick={() => setMode(value)}>{label}</button>)}
      </div>
      {result && <span className="terminal-tag terminal-ranges">{result.request.symbol} · {result.request.timeframe}</span>}
    </div>
    {ready ? <>
      <div className="terminal-quote"><strong>{MODES[chartMode]}</strong>
        <span className="terminal-price">{chartMode === 'drawdown' ? percent(point.drawdown_pct) : number(point.equity)}</span>
        {chartMode === 'equity' && <span className="muted">USDT</span>}
      </div>
      <div className="terminal-ohlc">
        <span>{timeLabel(point.ts, true)} (KST)</span>
        {chartMode === 'equity' && <span>매수 후 보유 <b>{number(point.benchmark_equity)} USDT</b></span>}
      </div>
      <canvas ref={canvasRef} role="img" aria-label={`백테스트 ${MODES[chartMode]}`} className="terminal-canvas"
        onPointerMove={event => { if (event.pointerType === 'mouse') pick(event) }} onClick={pick} />
      <div className="terminal-chart-footer">
        <div className="terminal-legend">{chartMode === 'equity' ? <>
          <span><i style={{ background: STRATEGY_COLOR }} />전략</span>
          <span><i style={{ background: BENCHMARK_COLOR }} />매수 후 보유</span>
        </> : <span><i style={{ background: DRAWDOWN_COLOR }} />고점 대비 낙폭</span>}</div>
        <input type="range" aria-label="결과 시각 탐색" aria-valuetext={timeLabel(point.ts, true)}
          min={0} max={rows.length - 1} value={selected ?? rows.length - 1} onChange={event => setIndex(Number(event.target.value))} />
        <span>KST</span>
      </div>
    </> : <div className="terminal-chart-empty" role="status">
      {loading ? '공개 시세로 전략을 검증하고 있습니다.' : result ? '표시할 시계열이 부족합니다.' : '검증 조건을 선택한 뒤 백테스트를 실행하세요.'}
    </div>}
  </section>
}
