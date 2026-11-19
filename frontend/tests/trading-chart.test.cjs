const test = require('node:test')
const assert = require('node:assert/strict')

test('candle windows preserve gaps and markers require a completed bar and matching symbol', async () => {
  const { windowBars, markersByBar } = await import('../lib/trading-chart.mjs')
  const rows = [[100], [200], [400]]
  const plot = windowBars(rows, 100, 3)
  assert.deepEqual(plot, { rows: [[200], [400]], start: 200, slots: 3 })
  const signal = { time: 201, symbol: 'BTC/USDT', kind: 'signal' }
  const news = { time: 477, kind: 'news' }
  const markers = [signal, news, { time: 299, symbol: 'ETH/USDT' }, { time: 301 }, { time: 500 }]
  assert.deepEqual([...markersByBar(plot.rows, 100, markers, 'BTC/USDT')], [[200, [signal]], [400, [news]]])
})
