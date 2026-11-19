const test = require('node:test')
const assert = require('node:assert/strict')

test('topic and source filters combine and markers use publication time only', async () => {
  const { filterNews, newsMarkers } = await import('../lib/intel-feed.mjs')
  const news = [
    { topic: 'macro', source: 'Fed', title_ko: '금리 발표', published: '2026-11-20T08:30:00Z', event_time: '2026-11-20T09:00:00Z' },
    { topic: 'macro', source: 'Reuters', event_time: '2026-11-20T09:00:00Z' },
    { topic: 'crypto', source: 'Fed' },
  ]
  assert.deepEqual(filterNews(news, 'macro', 'Fed'), [news[0]])
  assert.deepEqual(filterNews(news, 'crypto', 'Reuters'), [])
  assert.deepEqual(newsMarkers(filterNews(news, 'macro', '')), [
    { time: Date.parse('2026-11-20T08:30:00Z'), kind: 'news', label: '금리 발표' },
  ])
})

test('published news renders directional scores from signed input and distinguishes missing scores', async () => {
  const { impactScores } = await import('../lib/intel-feed.mjs')
  assert.deepEqual(impactScores({ score: -1.02 }), { up: 0, down: 1.02 })
  assert.deepEqual(impactScores({ score: 0.5 }), { up: 0.5, down: 0 })
  assert.deepEqual(impactScores({ score: 0.5, long_event_score: 0 }), { up: 0, down: 0 })
  assert.deepEqual(impactScores({}), { up: null, down: null })
})
