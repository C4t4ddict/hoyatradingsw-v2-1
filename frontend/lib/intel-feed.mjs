import { eventTime } from './trading-chart.mjs'

export function filterNews(items, topic, source) {
  return items.filter(item => (!topic || (item.topic || 'other') === topic)
    && (!source || item.source === source))
}

export function newsMarkers(items) {
  return items.flatMap(item => {
    const time = eventTime(item.event_time)
    return Number.isFinite(time) ? [{ time, kind: 'news', label: item.title_ko || item.title }] : []
  })
}
