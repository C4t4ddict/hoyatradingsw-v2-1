'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchJson } from '../../lib/api'
import { eventBar, markersByBar, number, percent, RANGES, SYMBOLS, timeLabel, windowBars } from '../../lib/trading-chart.mjs'

const MARGIN = { left: 12, right: 76, top: 14, bottom: 28 }
const COLORS = { up: '#35c995', down: '#ef777b', news: '#f0bd65', signal: '#88adff' }
const MARKERS = { news: ['뉴스', COLORS.news], signal: ['신호', COLORS.signal],
  buy: ['매수 체결', COLORS.up], sell: ['매도 체결', COLORS.down] }
const EMPTY = []

function drawPlot(canvas, plot, grouped, selected) {
  const { width, height } = canvas.getBoundingClientRect()
  if (!width || !height) return
  const dpr = window.devicePixelRatio || 1
  canvas.width = Math.round(width * dpr)
  canvas.height = Math.round(height * dpr)
  const ctx = canvas.getContext('2d')
  ctx.scale(dpr, dpr)
  const right = width - MARGIN.right
  const bottom = height - MARGIN.bottom
  const priceBottom = bottom - 60
  const cell = (right - MARGIN.left) / plot.slots
  const xAt = slot => MARGIN.left + (slot + 0.5) * cell
  const low = Math.min(...plot.rows.map(row => row[3]))
  const high = Math.max(...plot.rows.map(row => row[2]))
  const spread = Math.max(high - low, high * 0.002)
  const max = high + spread * 0.06
  const min = low - spread * 0.06
  const yAt = price => MARGIN.top + (max - price) / (max - min) * (priceBottom - MARGIN.top)
  const stroke = (x, y, endX, endY, color) => {
    ctx.strokeStyle = color
    ctx.beginPath()
    ctx.moveTo(x, y)
    ctx.lineTo(endX, endY)
    ctx.stroke()
  }
  ctx.font = '11px system-ui'
  ctx.textBaseline = 'middle'
  for (let level = 0; level <= 5; level++) {
    const price = max - level * (max - min) / 5
    const y = yAt(price)
    stroke(MARGIN.left, y, right, y, '#222c3c')
    ctx.fillStyle = '#a7b4c9'
    ctx.fillText(number(price, price < 10 ? 3 : 1), right + 7, y)
  }
  const stops = Math.min(5, plot.slots - 1, Math.floor((right - MARGIN.left) / 95))
  for (let step = 0; step <= stops && stops > 0; step++) {
    const slot = Math.round(step * (plot.slots - 1) / stops)
    const x = xAt(slot)
    stroke(x, MARGIN.top, x, bottom, '#222c3c')
    ctx.fillStyle = '#a7b4c9'
    const label = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', month: 'numeric', day: 'numeric' })
      .format(plot.start + slot * plot.interval)
    ctx.fillText(label, Math.max(MARGIN.left, Math.min(right - ctx.measureText(label).width, x - 12)), bottom + 14)
  }
  const maxVolume = Math.max(1, ...plot.rows.map(row => row[5]))
  const candleWidth = Math.max(1, Math.min(12, cell * 0.68))
  for (const [time, open, peak, floor, close, volume] of plot.rows) {
    const x = xAt((time - plot.start) / plot.interval)
    const color = close >= open ? COLORS.up : COLORS.down
    stroke(x, yAt(peak), x, yAt(floor), color)
    ctx.fillStyle = color
    ctx.fillRect(x - candleWidth / 2, Math.min(yAt(open), yAt(close)), candleWidth, Math.max(1, Math.abs(yAt(open) - yAt(close))))
    const volumeHeight = volume / maxVolume * 38
    ctx.globalAlpha = 0.42
    ctx.fillRect(x - candleWidth / 2, bottom - volumeHeight, candleWidth, volumeHeight)
    ctx.globalAlpha = 1
    const kinds = [...new Set((grouped.get(time) || []).map(marker => marker.kind))]
    kinds.forEach((kind, index) => {
      ctx.beginPath()
      ctx.arc(x, priceBottom + 7 + index * 8, Math.max(2, Math.min(3, cell / 2)), 0, Math.PI * 2)
      ctx.fillStyle = MARKERS[kind][1]
      ctx.fill()
    })
  }
  const lastClose = plot.rows.at(-1)[4]
  const priceY = yAt(lastClose)
  const priceLabel = number(lastClose, lastClose < 10 ? 3 : 2)
  ctx.setLineDash([4, 4])
  stroke(MARGIN.left, priceY, right, priceY, '#5b9e87')
  ctx.setLineDash([])
  ctx.fillStyle = '#217359'
  ctx.fillRect(right + 1, priceY - 9, ctx.measureText(priceLabel).width + 12, 18)
  ctx.fillStyle = '#fff'
  ctx.fillText(priceLabel, right + 7, priceY)
  if (selected != null) {
    const x = xAt((selected - plot.start) / plot.interval)
    ctx.setLineDash([3, 4])
    stroke(x, MARGIN.top, x, bottom, '#b1bfd6')
    ctx.setLineDash([])
  }
}

function Plot({ plot, grouped, selected, onPick }) {
  const ref = useRef(null)
  useEffect(() => {
    const canvas = ref.current
    const redraw = () => drawPlot(canvas, plot, grouped, selected)
    const observer = new ResizeObserver(redraw)
    observer.observe(canvas)
    redraw()
    return () => observer.disconnect()
  }, [plot, grouped, selected])

  return <canvas ref={ref} className="terminal-canvas" role="img" aria-label="확정 4시간봉과 거래량"
    onPointerMove={event => {
      if (event.pointerType !== 'mouse') return
      pick(event)
    }} onClick={pick} />

  function pick(event) {
    const bounds = event.currentTarget.getBoundingClientRect()
    const ratio = (event.clientX - bounds.left - MARGIN.left) / (bounds.width - MARGIN.left - MARGIN.right)
    if (ratio < 0 || ratio >= 1) return
    const time = plot.start + Math.floor(ratio * plot.slots) * plot.interval
    onPick(time)
  }
}

export default function CandleChart({ markers = EMPTY, mode = 'market', refresh = 0, focusEvent = null }) {
  const [symbol, setSymbol] = useState(SYMBOLS[0])
  const [range, setRange] = useState(RANGES[0].bars)
  const [response, setResponse] = useState(null)
  const [manual, setManual] = useState(null)
  useEffect(() => {
    let current = true
    fetchJson(`/api/runtime/candles?symbol=${encodeURIComponent(symbol)}`)
      .then(data => { if (current) setResponse({ symbol, refresh, data }) })
      .catch(() => { if (current) setResponse({ symbol, refresh, failed: true }) })
    return () => { current = false }
  }, [symbol, refresh])
  const result = response?.symbol === symbol && response.refresh === refresh ? response : null
  const interval = result?.data?.interval_ms
  const plot = useMemo(() => ({
    ...windowBars(result?.data?.rows || EMPTY, interval, range), interval,
  }), [result, interval, range])
  const grouped = useMemo(() => markersByBar(plot.rows, interval, markers, symbol), [plot, interval, markers, symbol])
  const focused = focusEvent ? eventBar(plot.rows, interval, focusEvent.time) : null
  const selected = manual?.focusEvent === focusEvent ? manual.time : focused
  const setSelected = time => setManual({ focusEvent, time })
  const index = plot.rows.findIndex(([time]) => time === selected)
  const active = selected == null ? plot.rows.at(-1) : plot.rows[index]
  const last = plot.rows.at(-1)
  const previous = plot.rows.at(-2)
  const change = last && previous && last[0] - previous[0] === interval ? (last[4] / previous[4] - 1) * 100 : null
  const legend = mode === 'paper' ? ['buy', 'sell'] : mode === 'intel' ? ['news'] : ['news', 'signal']
  const activeMarkers = grouped.get(active?.[0]) || []

  return <section className="terminal-panel terminal-chart" aria-label="가격 차트">
    <div className="terminal-chart-toolbar">
      <div className="terminal-switch" role="group" aria-label="차트 종목">{SYMBOLS.map(value =>
        <button type="button" key={value} aria-pressed={symbol === value} onClick={() => { setSymbol(value); setManual(null) }}>
          {value.split('/')[0]}
        </button>)}</div>
      <span className="terminal-tag">4시간봉</span>
      <div className="terminal-switch terminal-ranges" role="group" aria-label="차트 기간">{RANGES.map(option =>
        <button type="button" key={option.bars} aria-pressed={range === option.bars}
          onClick={() => { setRange(option.bars); setManual(null) }}>{option.label}</button>)}</div>
    </div>
    <div className="terminal-quote">
      <strong>{symbol}</strong>
      <span className="terminal-price">{number(last?.[4])}</span>
      <span className={change == null ? 'muted' : change >= 0 ? 'good' : 'bad'}>{change > 0 ? '+' : ''}{percent(change)}</span>
      {last && result.data.stale && <span className="terminal-tag warn">시세 지연</span>}
    </div>
    {last ? <>
      <div className="terminal-ohlc">
        <span>{active ? timeLabel(active[0]) : '결측 구간'} (KST)</span>
        {active && ['시가', '고가', '저가', '종가', '거래량'].map((label, i) =>
          <span key={label}>{label} <b>{number(active[i + 1])}</b></span>)}
      </div>
      {focusEvent && focused == null && <p className="terminal-summary" role="status">
        선택한 뉴스의 관측 시각에 표시할 확정 봉이 없습니다. 기간을 변경하면 이전 봉을 확인할 수 있습니다.
      </p>}
      <Plot plot={plot} grouped={grouped} selected={selected} onPick={setSelected} />
      <div className="terminal-chart-footer">
        <div className="terminal-legend">{legend.map(kind =>
          <span key={kind}><i style={{ backgroundColor: MARKERS[kind][1] }} />{MARKERS[kind][0]}</span>)}</div>
        <input type="range" aria-label="캔들 탐색" aria-valuetext={active ? timeLabel(active[0], true) : '결측 구간'}
          min={0} max={plot.rows.length - 1} value={index >= 0 ? index : plot.rows.length - 1}
          onChange={event => setSelected(plot.rows[Number(event.target.value)][0])} />
        <span>완료 봉 · KST</span>
      </div>
      {activeMarkers.length > 0 && <ul className="terminal-marker-detail">
        {activeMarkers.map((marker, index) => <li key={index}>{timeLabel(marker.time)} · {MARKERS[marker.kind][0]} · {marker.label}</li>)}
      </ul>}
    </> : <div className="terminal-chart-empty" role="status">
      {!result ? '확정 시세를 불러오는 중입니다.' : result.failed ? '시세를 불러오지 못했습니다.' : '수집된 확정 4시간봉이 없습니다.'}
    </div>}
  </section>
}
