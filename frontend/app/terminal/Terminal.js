'use client'

import { useId, useRef, useState } from 'react'
import { koBias, koTopic } from '../../lib/ko'
import { number, percent, safeNewsLink, timeLabel } from '../../lib/trading-chart.mjs'

export function MetricStrip({ items }) {
  return <dl className="terminal-metrics">{items.map(([label, value, tone]) =>
    <div key={label}><dt>{label}</dt><dd className={tone}>{value}</dd></div>
  )}</dl>
}

export function Tabs({ tabs }) {
  const [active, setActive] = useState(0)
  const id = useId()
  const buttons = useRef([])
  function navigate(event, index) {
    let next
    if (event.key === 'ArrowRight') next = (index + 1) % tabs.length
    else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length
    else if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = tabs.length - 1
    else return
    event.preventDefault()
    setActive(next)
    buttons.current[next]?.focus()
  }
  return <section className="terminal-panel terminal-tabs">
    <div className="terminal-tabs-bar" role="tablist" aria-label="상세 내역">
      {tabs.map(([label], index) => <button key={label} ref={el => { buttons.current[index] = el }}
        type="button" role="tab" id={`${id}-tab-${index}`} aria-controls={`${id}-panel`}
        aria-selected={index === active} tabIndex={index === active ? 0 : -1}
        onKeyDown={event => navigate(event, index)} onClick={() => setActive(index)}>{label}</button>)}
    </div>
    <div role="tabpanel" id={`${id}-panel`} aria-labelledby={`${id}-tab-${active}`} tabIndex={0}>
      {tabs[active][1]}
    </div>
  </section>
}

export function DetailTable({ columns, rows, empty = '표시할 기록이 없습니다.' }) {
  if (!rows.length) return <p className="terminal-empty">{empty}</p>
  return <div className="terminal-table-scroll" tabIndex={0}><table className="terminal-table">
    <thead><tr>{columns.map(label => <th key={label} scope="col">{label}</th>)}</tr></thead>
    <tbody>{rows.map(({ id, cells }) => <tr key={id}>
      {cells.map((cell, index) => <td key={columns[index]}>{cell}</td>)}
    </tr>)}</tbody>
  </table></div>
}

export function SignalResults({ signals }) {
  const totals = signals?.totals ?? []
  const labels = { intel_shadow: '뉴스 관찰', ml_shadow: 'ML 관찰', strategy_shadow: '전략 관찰' }
  return <>
    {totals.length > 0 && <div className="terminal-summary">{totals.map(row => <span key={row.kind}>
      {labels[row.kind] || row.kind} · 정산 {row.resolved} / {row.total}
    </span>)}</div>}
    <DetailTable columns={['관측 시각 (KST)', '종목', '출처', '기간', '방향', '결과', '비용 차감 수익률']}
      empty={signals ? '수집된 신호가 없습니다.' : '신호 기록을 불러오지 못했습니다.'}
      rows={(signals?.recent ?? []).map(row => ({ id: row.id, cells: [
        timeLabel(row.observed_ms), row.symbol, labels[row.kind] || row.kind, `${row.horizon}시간`,
        row.direction > 0 ? '상승' : '하락', row.net == null ? '정산 대기' : '정산 완료',
        percent(row.net, 100),
      ] }))} />
  </>
}

export function SignalDetails({ signal, brief }) {
  const scores = signal?.scores
  const ml = signal?.quality_policy?.ml_quality
  return <>
    <div className="terminal-panel-heading"><h2>시장 신호</h2>
      <span className="terminal-tag">{signal?.decision?.bias || brief?.bias
        ? koBias(signal?.decision?.bias || brief.bias) : '확인 불가'}</span></div>
    <dl className="terminal-facts">
      <div><dt>ML 검증</dt><dd>{ml ? ml.enabled ? '검증 통과' : '검증 대기' : '확인 불가'}</dd></div>
      <div><dt>검증 표본</dt><dd>{number(ml?.observations, 0)}</dd></div>
      <div><dt>ML 상승 / 하락</dt><dd>{number(scores?.ml_long_score)} / {number(scores?.ml_short_score)}</dd></div>
      {brief && <div><dt>뉴스 상승 / 하락</dt><dd>{number(brief.long_score)} / {number(brief.short_score)}</dd></div>}
    </dl>
  </>
}

export function NewsItem({ item }) {
  const link = safeNewsLink(item.link)
  const title = item.title_ko || item.title
  return <article className="terminal-news">
    <div className="terminal-news-meta">{item.source || '출처 미확인'} · {koTopic(item.topic)} · {timeLabel(item.published || item.event_time)}</div>
    {link ? <a href={link} target="_blank" rel="noreferrer" title={item.title}>{title} <span aria-hidden="true">↗</span></a> : <strong>{title}</strong>}
  </article>
}
