export const SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
export const RANGES = [{ label: '1주', bars: 42 }, { label: '1개월', bars: 180 }, { label: '3개월', bars: 540 }]

export function windowBars(rows, interval, bars) {
  const end = rows.at(-1)?.[0]
  if (end == null) return { rows: [], start: 0, slots: 0 }
  const start = Math.max(rows[0][0], end - (bars - 1) * interval)
  return { rows: rows.filter(([time]) => time >= start), start, slots: (end - start) / interval + 1 }
}

export function markersByBar(rows, interval, markers, symbol) {
  const byBar = new Map()
  const starts = new Set(rows.map(([time]) => time))
  for (const marker of markers) {
    if (!Number.isFinite(marker.time) || (marker.symbol && marker.symbol !== symbol)) continue
    const start = Math.floor(marker.time / interval) * interval
    if (!starts.has(start)) continue
    if (!byBar.has(start)) byBar.set(start, [])
    byBar.get(start).push(marker)
  }
  return byBar
}

export function eventBar(rows, interval, time) {
  if (!Number.isFinite(time) || !Number.isFinite(interval) || interval <= 0) return null
  const start = Math.floor(time / interval) * interval
  return rows.some(row => row[0] === start) ? start : null
}

export function eventTime(value) {
  return typeof value === 'number' ? value : value ? Date.parse(value) : NaN
}

export function number(value, digits = 2) {
  if (value == null || value === '' || !Number.isFinite(Number(value))) return '—'
  return Number(value).toLocaleString('ko-KR', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

export function percent(value, multiplier = 1) {
  return value == null || !Number.isFinite(Number(value)) ? '—' : `${number(value * multiplier)}%`
}

export function timeLabel(value, full = false) {
  const time = eventTime(value)
  if (!Number.isFinite(time)) return '—'
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul', ...(full ? { year: 'numeric' } : {}),
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).format(time)
}

export function safeNewsLink(value) {
  try {
    const url = new URL(value)
    return ['https:', 'http:'].includes(url.protocol) ? url.href : null
  } catch {
    return null
  }
}
