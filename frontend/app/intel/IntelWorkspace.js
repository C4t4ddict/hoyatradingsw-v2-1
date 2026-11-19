'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import { koBias, koTopic } from '../../lib/ko'
import { filterNews, newsMarkers } from '../../lib/intel-feed.mjs'
import { eventTime, number, percent, safeNewsLink, timeLabel } from '../../lib/trading-chart.mjs'
import CandleChart from '../terminal/CandleChart'
import { DetailTable, MetricStrip, SignalDetails, Tabs } from '../terminal/Terminal'
import './intel.css'

const HORIZONS = { '5m': '5분', '15m': '15분', '30m': '30분', '1h': '1시간', '4h': '4시간', '24h': '24시간' }
const READINESS = { ready: '사용 가능', needs_training: '학습 필요', collecting: '데이터 수집 중', blocked: '점검 필요' }
const TRIGGERS = { quality_gate: '품질 기준 미충족', live_intel: '시장 정보', ml: '뉴스 ML',
  market_pattern: '시장 패턴', combined: '복합 신호', none: '발동 신호 없음' }
const EMPTY = []

function targetLabel(value) {
  const match = /^label_(up|down)_(.+)$/.exec(value)
  return match ? `${HORIZONS[match[2]] || match[2]} ${match[1] === 'up' ? '상승' : '하락'}` : value
}

function Facts({ items }) {
  return <dl className="intel-facts">{items.map(([label, value]) =>
    <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
}

function EventDetail({ item }) {
  if (!item) return <p className="terminal-empty">뉴스를 선택하면 발행·관측 시각과 원문을 볼 수 있습니다.</p>
  const href = safeNewsLink(item.link)
  return <div className="intel-event-detail">
    <p className="intel-item-meta">발행 {timeLabel(item.published)} · 관측 {timeLabel(item.event_time)} KST</p>
    <strong>{item.title_ko || item.title || '제목 없음'}</strong>
    {item.title_ko && item.title_ko !== item.title && <p className="intel-item-meta">{item.title}</p>}
    <div className="intel-scores">
      <span className="good">상승 {number(item.long_event_score)}</span><span className="bad">하락 {number(item.short_event_score)}</span>
      {href && <a href={href} target="_blank" rel="noreferrer">원문 열기 ↗</a>}
    </div>
  </div>
}

function NewsPanel({ rows, shown, topic, setTopic, source, setSource, selected, selectItem, recovered }) {
  const topics = [...new Set(rows.map(item => item.topic || 'other'))]
  const sources = [...new Set(rows.map(item => item.source).filter(Boolean))].sort()
  return <aside className="terminal-panel terminal-context intel-panel" aria-label="시장 뉴스">
    <div className="terminal-panel-heading"><h2>시장 뉴스</h2><span className="terminal-tag">{shown.length} / {rows.length}건</span></div>
    <p className="intel-item-meta">시장 공통 이벤트 · 상위 뉴스 기준</p>
    <div className="intel-filters">
      <label>주제<select value={topic} onChange={event => setTopic(event.target.value)}>
        <option value="">전체 주제</option>
        {topics.map(value => <option key={value} value={value}>{koTopic(value)}</option>)}
      </select></label>
      <label>출처<select value={source} onChange={event => setSource(event.target.value)}>
        <option value="">전체 출처</option>
        {sources.map(value => <option key={value}>{value}</option>)}
      </select></label>
    </div>
    <div className="intel-feed" aria-label="뉴스 목록">
      {shown.length ? shown.map((item, index) => <button key={item.event_id || index} type="button"
        aria-pressed={selected === item} onClick={() => selectItem(item)}>
        <span className="intel-item-meta">{koTopic(item.topic)} · {item.source || '출처 미확인'}</span>
        <strong>{item.title_ko || item.title || '제목 없음'}</strong>
      </button>) : <p className="terminal-empty">{recovered ? '조건에 맞는 뉴스가 없습니다.' : '뉴스를 불러오지 못했습니다.'}</p>}
    </div>
    {recovered && <EventDetail item={selected} />}
  </aside>
}

function SignalPanel({ signal, brief, quality }) {
  const predictions = signal?.predictions
  const probabilities = Object.entries(HORIZONS).map(([key, label]) => {
    const up = predictions?.[`label_up_${key}`]
    const down = predictions?.[`label_down_${key}`]
    return { id: key, cells: [label,
      up?.ok === true ? percent(up.positive_proba, 100) : '검증 대기',
      down?.ok === true ? percent(down.positive_proba, 100) : '검증 대기',
    ] }
  })
  return <>
    <div className="intel-signal-overview">
      <div><SignalDetails signal={signal} brief={brief} /></div>
      <Facts items={[
        ['신호 정책', quality?.signals_enabled === true ? '검증 신호 사용' : quality ? '관찰 모드' : '확인 불가'],
        ['판단 근거', TRIGGERS[signal?.decision?.trigger_source] || signal?.decision?.trigger_source || '—'],
        ['시장 정보 가중치', percent(quality?.weights?.intel, 100)], ['ML 가중치', percent(quality?.weights?.ml, 100)],
        ['허용 노출', percent(signal?.decision?.position_size_multiplier, 100)],
        ['뉴스 검증 표본', number(quality?.intel_quality?.observations, 0)],
        ['뉴스 Brier 점수', number(quality?.intel_quality?.brier_score, 3)],
        ['ML Brier 점수', number(quality?.ml_quality?.brier_score, 3)],
      ]} />
    </div>
    <DetailTable columns={['뉴스 모델 예측 구간', '상승 확률', '하락 확률']}
      rows={predictions ? probabilities : EMPTY} empty="뉴스 모델의 예측 기록이 없습니다." />
  </>
}

function ReadinessPanel({ readiness, pattern = false }) {
  if (!readiness) return <p className="terminal-empty">모델 준비 상태를 불러오지 못했습니다.</p>
  const dataset = readiness.dataset
  const models = readiness.models
  const thresholds = readiness.thresholds
  const common = [
    ['준비 상태', READINESS[readiness.status] || readiness.status || '—'],
    ['관측 데이터 / 최소', `${number(dataset?.rows, 0)} / ${number(thresholds?.minimum_rows, 0)}`],
    ['검증 모델 / 필요', `${number(models?.validated, 0)} / ${number(models?.required, 0)}`],
  ]
  const facts = pattern ? [
    ...common, ['시작 (KST)', timeLabel(dataset?.started_at, true)], ['종료 (KST)', timeLabel(dataset?.ended_at, true)],
    ['최신 패턴 방향', readiness.latest_prediction?.bias ? koBias(readiness.latest_prediction.bias) : '—'],
  ] : [...common, ['중복 이벤트', number(dataset?.duplicate_events, 0)], ['시점 누수', number(dataset?.feature_leakage_rows, 0)]]
  const columns = pattern ? ['예측 구간', '라벨 수', '양성 / 음성', '균형 정확도', '비용 반영 Sharpe', '워크포워드', '검증']
    : ['예측 구간', '라벨 수', '양성 / 음성', '데이터 준비', '검증']
  return <>
    <Facts items={facts} />
    {readiness.blockers?.length > 0 && <div className="intel-blockers">
      <strong>차단 사유</strong><ul>{readiness.blockers.map((reason, index) => <li key={index}>{reason}</li>)}</ul>
    </div>}
    <DetailTable columns={columns} empty="모델별 검증 기록이 없습니다."
      rows={(readiness.targets ?? []).map(target => ({ id: target.target, cells: [
        targetLabel(target.target), number(target.rows, 0), `${number(target.positives, 0)} / ${number(target.negatives, 0)}`,
        ...(pattern ? [number(target.balanced_accuracy, 3), number(target.net_sharpe),
          target.walk_forward_passed_folds == null ? '—' : `${target.walk_forward_passed_folds} / ${target.walk_forward_required_passes}`]
          : [target.data_ready ? '충족' : '부족']),
        target.model_validated ? '통과' : '대기',
      ] }))} />
  </>
}

function CollectionPanel({ brief }) {
  const status = brief?.collection_status
  if (!status) return <p className="terminal-empty">수집 상태를 불러오지 못했습니다.</p>
  const failed = status.failed ?? EMPTY
  const timedOut = status.timed_out ?? EMPTY
  return <>
    <Facts items={[
      ['전체 출처', number(status.sources, 0)],
      ['정상 응답', status.completed == null ? '—' : number(Math.max(0, status.completed - failed.length), 0)],
      ['시간 초과', number(timedOut.length, 0)], ['실패', number(failed.length, 0)],
      ['소요 시간 (ms)', number(status.elapsed_ms)], ['캐시 상태', brief.stale ? '이전 브리핑으로 대체' : '유효 브리핑'],
    ]} />
    <DetailTable columns={['출처', '상태', '오류']} empty="기록된 실패와 시간 초과가 없습니다."
      rows={[
        ...failed.map((entry, index) => ({ id: `failure-${index}`, cells: [entry.source, '실패', entry.error || '—'] })),
        ...timedOut.map((name, index) => ({ id: `timeout-${index}`, cells: [name, '시간 초과', '—'] })),
      ]} />
  </>
}

export default function IntelWorkspace({ data }) {
  const [topic, setTopic] = useState('')
  const [source, setSource] = useState('')
  const [picked, setPicked] = useState(null)
  const brief = data?.market_brief
  const signal = data?.ml_signal
  const quality = data?.signal_quality || signal?.quality_policy
  const readiness = data?.ml_readiness
  const rows = brief?.top ?? EMPTY
  const shown = useMemo(() => filterNews(rows, topic, source), [rows, topic, source])
  const markers = useMemo(() => newsMarkers(shown), [shown])
  const selected = shown.includes(picked?.item) ? picked.item : null
  const direction = signal?.decision?.bias || brief?.bias
  const status = brief?.collection_status
  const problems = (status?.failed?.length ?? 0) + (status?.timed_out?.length ?? 0)
  const feedState = !brief ? '브리핑 확인 불가' : brief.stale ? '이전 캐시 사용'
    : !status ? '수집 상태 미확인' : problems ? `수집 지연·실패 ${problems}건` : '수집 정상'

  return <div className="terminal">
    <header className="terminal-header">
      <div><p className="terminal-eyebrow">HOYA / 시장 정보</p><h1>시장 인텔리전스</h1></div>
      <div className="terminal-header-actions">
        <span className={feedState === '수집 정상' ? 'terminal-tag good' : 'terminal-tag warn'}>{feedState}</span>
        <Link href="/" className="terminal-link">대시보드 ↗</Link>
      </div>
    </header>
    <MetricStrip items={[
      ['종합 방향', direction ? koBias(direction) : '—'],
      ['뉴스 상승 점수', number(brief?.long_score), 'good'],
      ['뉴스 하락 점수', number(brief?.short_score), 'bad'],
      ['ML 검증 표본', number(quality?.ml_quality?.observations, 0)],
      ['브리핑 갱신 (KST)', timeLabel(brief?.updated_at)],
    ]} />
    <div className="terminal-workspace">
      <CandleChart mode="intel" markers={markers} focusEvent={selected ? picked : null} />
      <NewsPanel rows={rows} shown={shown} topic={topic} source={source} selected={selected} recovered={Boolean(brief)}
        setTopic={value => { setTopic(value); setPicked(null) }} setSource={value => { setSource(value); setPicked(null) }}
        selectItem={item => setPicked({ item, time: eventTime(item.event_time) })} />
    </div>
    <Tabs tabs={[
      ['신호 품질', <SignalPanel key="quality" signal={signal} brief={brief} quality={quality} />],
      ['뉴스 ML', <ReadinessPanel key="news" readiness={readiness} />],
      ['과거 패턴', <ReadinessPanel key="pattern" readiness={readiness?.market_pattern} pattern />],
      ['수집 상태', <CollectionPanel key="collection" brief={brief} />],
    ]} />
  </div>
}
