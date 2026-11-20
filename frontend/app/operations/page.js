'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { API_BASE } from '../../lib/api'
import { koAlertMessage, koCategory, koStatus } from '../../lib/ko'
import { number, timeLabel } from '../../lib/trading-chart.mjs'
import { canConfirmLive, operationError } from '../../lib/operations-control.mjs'
import { DetailTable, MetricStrip, SignalResults, Tabs } from '../terminal/Terminal'
import { CampaignHistory, JobHistory, MarketStatus } from './RuntimePanel'
import '../terminal/terminal.css'
import './operations.css'

const SOURCES = {
  ops: '/api/operations', security: '/api/security/status', live: '/api/live/status', runtime: '/api/runtime',
}
const SECRET_NAMES = [
  'API_KEY', 'API_SECRET', 'WEBHOOK_TOKEN', 'ALERT_TELEGRAM_BOT_TOKEN', 'ALERT_TELEGRAM_CHAT_ID',
  'PAPER_ALERT_TELEGRAM_BOT_TOKEN', 'PAPER_ALERT_TELEGRAM_CHAT_ID',
]
const ACTION_LABELS = {
  live_challenge_requested: '1차 실거래 확인', live_enabled: '실거래 활성화', live_disabled: '모의투자 전환',
  live_expired: '실거래 만료', order_cap_changed: '건당 주문 상한 변경',
  session_checkpoint: '세션 체크포인트', session_started: '세션 시작', order_filled: '주문 체결',
}
const statusText = (value, yes, no) => value === true ? yes : value === false ? no : '미확인'
const tone = value => value === true ? 'good' : value === false ? 'bad' : 'warn'

async function readStatus(path, signal, settingsToken) {
  const headers = settingsToken ? { 'X-Settings-Token': settingsToken } : undefined
  const response = await fetch(`${API_BASE}${path}`, { cache: 'no-store', signal, headers })
  if (!response.ok) throw new Error('상태 조회 실패')
  return response.json()
}

function Alerts({ ops }) {
  return <DetailTable columns={['상태', '심각도', '분류', '마지막 감지 (KST)', '횟수', '메시지']}
    empty={ops ? '기록된 운영 경보가 없습니다.' : '운영 경보 미확인'}
    rows={(ops?.alerts ?? []).slice(0, 30).map(row => ({ id: row.alert_id, cells: [
      koStatus(row.status), <span key="severity" className={row.severity === 'critical' ? 'bad' : row.severity === 'warning' ? 'warn' : 'muted'}>{koStatus(row.severity)}</span>,
      koCategory(row.category), timeLabel(row.last_seen_at), number(row.occurrence_count, 0), koAlertMessage(row.message),
    ] }))} />
}

function Audit({ live, audit }) {
  return <>
    <h2 className="ops-subheading">설정 변경 이력</h2>
    <DetailTable columns={['변경 시각 (KST)', '작업자', '변경 내용']} empty={live ? '설정 변경 기록이 없습니다.' : '설정 기록 미확인'}
      rows={(live?.history ?? []).slice(0, 20).map(row => ({ id: row.sequence, cells: [
        timeLabel(row.changed_at, true), row.actor, ACTION_LABELS[row.action] || row.action,
      ] }))} />
    <h2 className="ops-subheading">감사 이벤트</h2>
    <DetailTable columns={['발생 시각 (KST)', '유형', '전략 버전']} empty={audit ? '감사 기록이 없습니다.' : '감사 기록 미확인'}
      rows={(audit?.recent_events ?? []).slice(0, 20).map(row => ({ id: row.event_id, cells: [
        timeLabel(row.occurred_at, true), ACTION_LABELS[row.event_type] || row.event_type, row.strategy_version || '—',
      ] }))} />
  </>
}

function Vault({ security, locked, store }) {
  const form = useRef(null)
  const ready = security?.vault?.encryption_configured
  const saved = new Set((security?.vault?.secrets ?? []).map(row => row.name))
  return <>
    <form ref={form} className="terminal-context ops-vault-form" onSubmit={event => {
      event.preventDefault()
      const data = new FormData(event.currentTarget)
      store({ name: data.get('name'), value: data.get('value') }, () => form.current?.reset())
    }}>
      <div className="terminal-panel-heading"><h2>암호화 보관함</h2><span className={`terminal-tag ${ready ? 'good' : 'warn'}`}>
        {statusText(ready, '마스터 키 준비', '마스터 키 필요')}</span></div>
      <div className="ops-fields">
        <label>자격증명 종류<select name="name">{SECRET_NAMES.map(name => <option key={name}>{name}</option>)}</select></label>
        <label>저장할 값<input name="value" type="password" required maxLength={4096} autoComplete="new-password" /></label>
        <button type="submit" className="ops-button" disabled={locked || ready !== true}>암호화 저장</button>
      </div>
    </form>
    <DetailTable columns={['자격증명', '보관함 상태']} rows={SECRET_NAMES.map(name => ({ id: name,
      cells: [name, security ? saved.has(name) ? '저장됨' : '미저장' : '미확인'],
    }))} />
  </>
}

export default function OperationsPage() {
  const [data, setData] = useState({})
  const [unavailable, setUnavailable] = useState([])
  const [busy, setBusy] = useState(false)
  const [settingsToken, setSettingsToken] = useState('')
  const [cap, setCap] = useState('')
  const [challenge, setChallenge] = useState(null)
  const [feedback, setFeedback] = useState(null)
  const inflight = useRef(false)

  async function refresh(keys, signal) {
    const results = await Promise.allSettled(keys.map(key => readStatus(SOURCES[key], signal, settingsToken)))
    if (signal?.aborted) return false
    const failed = keys.filter((_, index) => results[index].status === 'rejected')
    const next = Object.fromEntries(keys.map((key, index) => [key, results[index].status === 'fulfilled' ? results[index].value : null]))
    setData(current => ({ ...current, ...next }))
    setUnavailable(current => [...current.filter(key => !keys.includes(key)), ...failed])
    if (keys.includes('live')) setCap(next.live?.control?.max_order_usdt ?? '')
    return failed.length === 0
  }

  useEffect(() => {
    const controller = new AbortController()
    refresh(['security', 'live', 'runtime'], controller.signal)
    const timer = setInterval(() => {
      if (!inflight.current) refresh(['runtime'], controller.signal)
    }, 15000)
    return () => { clearInterval(timer); controller.abort() }
  }, [])

  useEffect(() => {
    if (!challenge?.expires) return
    const timer = setTimeout(() => setChallenge(null), Math.max(0, Date.parse(challenge.expires) - Date.now()))
    return () => clearTimeout(timer)
  }, [challenge])

  async function perform(path, body, onSuccess) {
    if (inflight.current || (path && !settingsToken)) return
    inflight.current = true
    setBusy(true)
    setFeedback(null)
    try {
      let payload = null
      if (path) {
        const response = await fetch(`${API_BASE}${path}`, {
          method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Settings-Token': settingsToken },
          body: body == null ? undefined : JSON.stringify(body),
        })
        if (!response.ok) throw new Error(operationError(response.status))
        payload = await response.json().catch(() => null)
      }
      const updated = await refresh(Object.keys(SOURCES).filter(key => key !== 'ops' || settingsToken))
      const message = path ? onSuccess?.(payload) || '요청이 반영되었습니다.' : '최신 상태를 확인했습니다.'
      setFeedback(updated ? { message } : { message: path ? `${message} 일부 상태를 새로고침하지 못했습니다.` : '일부 상태를 새로고침하지 못했습니다.', warning: true })
    } catch (error) {
      setFeedback({ message: error instanceof TypeError ? operationError() : error.message, warning: true })
    } finally {
      inflight.current = false
      setBusy(false)
    }
  }

  const { ops, security, live, runtime } = data
  const control = live?.control ?? security?.live_control
  const audit = ops?.audit
  const worker = audit?.worker
  const integrity = audit?.ledger_integrity
  const collector = runtime?.worker
  const state = !collector ? '미확인' : !collector.enabled ? '일시정지' : collector.alive ? '실행 중' : '미실행'
  const mode = statusText(control?.live_enabled, '실거래 활성', '모의투자 보호')
  const runtimeErrors = runtime?.jobs?.filter(job => job.error).length
  const locked = busy || !settingsToken
  const canConfirm = canConfirmLive(control, challenge, Boolean(settingsToken))
  const validCap = Number.isFinite(Number(cap)) && Number(cap) > 0

  useEffect(() => {
    const deadline = Date.parse(control?.expires_at)
    if (!Number.isFinite(deadline)) return
    const controller = new AbortController()
    const timer = setTimeout(() => refresh(['live', 'security'], controller.signal), Math.max(0, deadline - Date.now()))
    return () => { clearTimeout(timer); controller.abort() }
  }, [control?.expires_at])

  function challengeLive() {
    perform('/api/live/challenge', { confirmation: 'I UNDERSTAND LIVE ORDERS' }, result => {
      if (result?.challenge_token) {
        setChallenge({ token: result.challenge_token, expires: result.expires_at })
        return '1차 확인 완료. 5분 안에 2차 확인을 진행하세요.'
      }
    })
  }

  function confirmLive() {
    if (!canConfirmLive(control, challenge, Boolean(settingsToken))) return
    perform('/api/live/confirm', { challenge_token: challenge.token, confirmation: 'ENABLE LIVE TRADING', duration_minutes: 240 }, result => {
      if (result?.live_enabled) setChallenge(null)
    })
  }

  return <div className="terminal ops-terminal">
    <header className="terminal-header">
      <div><p className="terminal-eyebrow">HOYA / 시스템 운영</p><h1>운영·보안</h1></div>
      <div className="terminal-header-actions">
        <span className={`terminal-tag ${control?.live_enabled === false ? 'good' : 'warn'}`}>{mode}</span>
        <button type="button" className="ops-button" disabled={busy} onClick={() => perform(null)}>새로고침</button>
      </div>
    </header>
    <MetricStrip items={[
      ['수집기', state, state === '실행 중' ? 'good' : 'warn'],
      ['모의투자 작업자', statusText(worker?.alive, '실행 중', '중지'), tone(worker?.alive)],
      ['원장 무결성', statusText(integrity?.ok, '정상', '실패'), tone(integrity?.ok)],
      ['활성 경보', number(ops?.active_count, 0), ops?.active_count > 0 ? 'warn' : undefined],
      ['세션 갱신 (KST)', timeLabel(audit?.last_update)],
    ]} />
    {unavailable.length > 0 && <p className="ops-notice warn" role="status">일부 상태를 불러오지 못했습니다. 미확인 항목을 새로고침할 수 있습니다.</p>}
    {feedback && <p className={`ops-notice ${feedback.warning ? 'warn' : 'good'}`} role={feedback.warning ? 'alert' : 'status'}>{feedback.message}</p>}
    <div className="terminal-workspace">
      <section className="terminal-panel ops-main-panel">
        <div className="ops-panel-heading terminal-panel-heading"><h2>시장 데이터 수집</h2><span className="terminal-tag">15초 간격 갱신</span></div>
        <MarketStatus runtime={runtime} />
        <div className="terminal-summary">
          <span>수집 오류 {number(runtimeErrors, 0)}건</span><span>원장 검증 {number(integrity?.events_checked, 0)}건</span>
          <span>위험 경보 {number(ops?.critical_count, 0)}건</span>
        </div>
        <div className="terminal-context terminal-divider ops-tasks">
          <h2>수집·세션 제어</h2>
          <div className="ops-actions">{[['resume', '수집 재개'], ['pause', '수집 일시정지'], ['retry', '실패 작업 재시도']].map(([action, label]) =>
            <button key={action} type="button" className="ops-button" disabled={locked} onClick={() => perform('/api/runtime/control', { action })}>{label}</button>)}
            <button type="button" className="ops-button" disabled={locked} onClick={() => perform('/api/paper/resume')}>기존 모의투자 재개</button>
          </div>
          <h2>원장·일간 리포트</h2>
          <div className="ops-actions">
            <button type="button" className="ops-button" disabled={locked} onClick={() => perform('/api/paper/ledger/backup', null,
              result => result?.path && `백업 파일 · ${result.path}`)}>원장 백업</button>
            <button type="button" className="ops-button" disabled={locked} onClick={() => perform('/api/paper/ledger/export', null,
              result => result?.path && `CSV 파일 · ${result.path}`)}>CSV 내보내기</button>
            <button type="button" className="ops-button" disabled={locked} onClick={() => perform('/api/operations/daily-report/send', null,
              result => result?.notified_at ? `리포트 생성 완료 · 마지막 알림 ${timeLabel(result.notified_at)} (KST)`
                : '리포트 생성 완료 · 전송 기록 없음')}>일간 리포트 전송</button>
          </div>
        </div>
      </section>
      <aside className="terminal-panel terminal-context ops-control" aria-label="실거래 안전 제어">
        <div className="terminal-panel-heading"><h2>실거래 안전 제어</h2><Link href="/risk">위험 정책 ↗</Link></div>
        <p className="ops-muted">설정 토큰과 두 번의 확인이 필요합니다. 활성화 후 4시간에 자동 만료됩니다.</p>
        <label>설정 토큰<input type="password" value={settingsToken} disabled={busy} autoComplete="off"
          onChange={event => { setSettingsToken(event.target.value); setChallenge(null) }} /></label>
        <form className="ops-cap" onSubmit={event => { event.preventDefault(); if (validCap) perform('/api/live/order-cap', { max_order_usdt: Number(cap) }) }}>
          <label>건당 주문 상한 (USDT)<input type="number" min="0" step="any" value={cap} disabled={busy} onChange={event => setCap(event.target.value)} /></label>
          <button type="submit" className="ops-button" disabled={locked || !validCap}>상한 저장</button>
        </form>
        <dl className="terminal-facts">
          <div><dt>1차 확인</dt><dd>{canConfirm ? `완료 · ${timeLabel(challenge.expires)}` : '확인 대기'}</dd></div>
          <div><dt>실거래 만료 (KST)</dt><dd>{timeLabel(control?.expires_at)}</dd></div>
        </dl>
        <div className="ops-actions ops-control-actions">
          <button type="button" className="ops-button" disabled={locked || control?.live_enabled !== false} onClick={challengeLive}>1차 실거래 확인</button>
          <button type="button" className="ops-button ops-danger" disabled={locked || !canConfirm} onClick={confirmLive}>2차 실거래 활성화</button>
          <button type="button" className="ops-button" disabled={locked || !control?.live_enabled} onClick={() => perform('/api/live/disable', null, () => setChallenge(null))}>즉시 모의투자 전환</button>
        </div>
      </aside>
    </div>
    <Tabs tabs={[
      ['운영 경보', <Alerts key="alerts" ops={ops} />],
      ['수집 로그', <JobHistory key="jobs" runtime={runtime} />],
      ['세션 평가', <CampaignHistory key="campaigns" runtime={runtime} />],
      ['신호 결과', <SignalResults key="signals" signals={runtime?.signals} />],
      ['설정·감사', <Audit key="audit" live={live} audit={audit} />],
      ['자격증명', <Vault key="vault" security={security} locked={locked} store={(body, reset) =>
        perform('/api/security/secrets', body, result => { if (result?.stored) reset() })} />],
    ]} />
  </div>
}
