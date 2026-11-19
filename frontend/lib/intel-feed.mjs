import { eventTime } from './trading-chart.mjs'

export function filterNews(items, topic, source) {
  return items.filter(item => (!topic || (item.topic || 'other') === topic)
    && (!source || item.source === source))
}

export function impactScores(item) {
  const signed = Number.isFinite(item.score) ? item.score : null
  return {
    up: item.long_event_score ?? (signed == null ? null : Math.max(0, signed)),
    down: item.short_event_score ?? (signed == null ? null : Math.max(0, -signed)),
  }
}

export function newsMarkers(items) {
  return items.flatMap(item => {
    const time = eventTime(item.published)
    return Number.isFinite(time) ? [{ time, kind: 'news', label: item.title_ko || item.title }] : []
  })
}
