'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { API_BASE } from '../../lib/api'
import { koPosition, koStatus } from '../../lib/ko'
import { accountSnapshot } from '../../lib/account-snapshot.mjs'
import { number, percent, timeLabel } from '../../lib/trading-chart.mjs'
import { DetailTable, MetricStrip, Tabs } from '../terminal/Terminal'
import './account.css'

const ORDER_TYPES = { market: '시장가', limit: '지정가', stop_market: '스탑 시장가', stop: '스탑' }
const ORDER_STATES = { open: '대기', new: '대기', partially_filled: '부분 체결', canceled: '취소' }
const pnlTone = value => value == null ? undefined : value >= 0 ? 'good' : 'bad'
const lookupError = status => status === 401 || status === 403 ? '웹훅 토큰을 확인하세요.'
  : '비공개 계정 데이터를 불러오지 못했습니다. 서버 설정을 확인한 뒤 다시 조회하세요.'

function CashBreakdown({ balance }) {
  const free = balance?.free
  const used = balance?.used
  const ratio = free != null && used != null && free >= 0 && used >= 0 && free + used > 0 ? used / (free + used) : null
  return <div className="account-balances">
    <dl>
      <div><dt>사용 가능 (USDT)</dt><dd>{number(free)}</dd></div>
      <div><dt>사용 중 (USDT)</dt><dd>{number(used)}</dd></div>
      <div><dt>총액 (USDT)</dt><dd>{number(balance?.total)}</dd></div>
    </dl>
    {ratio != null && <meter min={0} max={1} value={ratio} aria-label="사용 중인 잔액 비율" aria-valuetext={percent(ratio, 100)} />}
  </div>
}

function Positions({ snapshot }) {
  const rows = snapshot?.positions
  return <DetailTable columns={['종목', '방향', '계약 수량', '진입가', '기준가', '미실현 손익 (USDT)']}
    empty={!snapshot ? '웹훅 토큰으로 조회하면 비공개 포지션이 표시됩니다.'
      : !rows ? '포지션 조회에 실패했습니다.' : '열린 포지션이 없습니다.'}
    rows={(rows ?? []).slice(0, 20).map((row, index) => ({ id: index, cells: [
      row.symbol || '—', koPosition(row.side), number(row.contracts, 8), number(row.entryPrice), number(row.markPrice),
      <span key="pnl" className={pnlTone(row.unrealizedPnl)}>{number(row.unrealizedPnl)}</span>,
    ] }))} />
}

function AccountOrders({ snapshot }) {
  return <DetailTable columns={['종목', '방향', '주문 유형', '수량', '주문가', '상태']}
    empty={!snapshot ? '비공개 계정을 조회하면 미체결 주문이 표시됩니다.'
      : !snapshot.orders ? '미체결 주문 조회에 실패했습니다.' : '미체결 주문이 없습니다.'}
    rows={(snapshot?.orders ?? []).slice(0, 20).map((row, index) => ({ id: index, cells: [
      row.symbol || '—', koPosition(row.side), ORDER_TYPES[row.type] || row.type || '—',
      number(row.amount, 8), number(row.price), ORDER_STATES[row.status] || koStatus(row.status),
    ] }))} />
}

function PaperAccount({ paper }) {
  const state = !paper ? '미확인' : paper.paused ? '일시정지' : paper.running ? '운용 중' : '중지'
  const metrics = paper?.metrics
  return <>
    <div className="terminal-summary"><span>가상 계정 · {state}</span>
      <span>가상 자산 {number(metrics?.virtual_balance)} USDT</span><span>가상 현금 {number(paper?.portfolio?.cash)} USDT</span>
      <span>수익률 {percent(metrics?.return_pct)}</span><span>기록된 실현 손익 {number(metrics?.realized_pnl)} USDT</span>
      <span>갱신 {timeLabel(paper?.last_update)} (KST)</span></div>
    <DetailTable columns={['모의 보유 종목', '수량', '평균 취득가 (USDT)']}
      empty={paper?.portfolio ? '현재 모의 보유 종목이 없습니다.' : '모의투자 보유 상태 미확인'}
      rows={(paper?.portfolio?.positions ?? []).map(row => ({ id: row.symbol,
        cells: [row.symbol, number(row.units, 8), number(row.average_cost)] }))} />
  </>
}

export default function AccountWorkspace({ paper, vaultNames }) {
  const [snapshot, setSnapshot] = useState(null)
  const [phase, setPhase] = useState('locked')
  const [feedback, setFeedback] = useState('')
  const [hasToken, setHasToken] = useState(false)
  const input = useRef(null)
  const active = useRef(null)
  useEffect(() => () => active.current?.abort(), [])

  async function lookup(event) {
    event.preventDefault()
    if (active.current || !input.current.value.trim()) return
    const token = input.current.value
    input.current.value = ''
    setHasToken(false)
    const controller = new AbortController()
    active.current = controller
    setPhase('loading')
    setFeedback('')
    setSnapshot(null)
    try {
      const response = await fetch(`${API_BASE}/api/account?market_type=futures`, {
        cache: 'no-store', headers: { 'X-Webhook-Token': token }, signal: controller.signal,
      })
      if (!response.ok) throw new Error(lookupError(response.status))
      const data = accountSnapshot(await response.json())
      if (!data?.received) throw new Error(lookupError())
      if (active.current !== controller) return
      setSnapshot({ ...data, timestamp: Date.now() })
      setPhase(data.complete ? 'ready' : 'partial')
    } catch (error) {
      if (active.current !== controller) return
      setPhase('failed')
      setFeedback(error.message === lookupError(401) ? error.message : lookupError())
    } finally {
      if (active.current === controller) active.current = null
    }
  }

  function clearSnapshot() {
    active.current?.abort()
    active.current = null
    input.current.value = ''
    setHasToken(false)
    setSnapshot(null)
    setFeedback('')
    setPhase('locked')
  }

  const labels = { locked: '비공개 데이터 잠김', loading: '조회 중', ready: '조회 완료', partial: '부분 조회', failed: '조회 실패' }
  const vaultReady = vaultNames?.includes('API_KEY') && vaultNames?.includes('API_SECRET')
  return <div className="terminal account-terminal">
    <header className="terminal-header">
      <div><p className="terminal-eyebrow">HOYA / 자산</p><h1>계정</h1></div>
      <div className="terminal-header-actions">
        <span className={`terminal-tag ${phase === 'ready' ? 'good' : phase === 'failed' ? 'bad' : 'warn'}`} role="status">{labels[phase]}</span>
        <Link className="terminal-link" href="/paper">모의투자 ↗</Link>
      </div>
    </header>
    <MetricStrip items={[
      ['계정 유형', 'USDT 무기한 선물'],
      ['비공개 총액 (USDT)', number(snapshot?.balance?.total)],
      ['보유 포지션', number(snapshot?.positions?.length, 0)],
      ['미실현 손익 (USDT)', number(snapshot?.pnl), pnlTone(snapshot?.pnl)],
      ['응답 시각 (KST)', timeLabel(snapshot?.timestamp)],
    ]} />
    <div className="terminal-workspace">
      <section className="terminal-panel" aria-label="비공개 선물 계정">
        <div className="account-panel-heading terminal-panel-heading"><h2>비공개 계정 잔액</h2><span className="terminal-tag">USDT</span></div>
        <CashBreakdown balance={snapshot?.balance} />
        {snapshot && !snapshot.parts.balance && <p className="terminal-summary warn">USDT 잔액 내역을 확인할 수 없습니다.</p>}
        <div className="account-panel-heading terminal-panel-heading"><h2>인증된 포지션</h2>
          {snapshot?.positions?.length > 20 && <span className="terminal-tag">최대 20건 표시</span>}</div>
        <Positions snapshot={snapshot} />
      </section>
      <aside className="terminal-panel terminal-context account-auth" aria-label="비공개 계정 인증">
        <div className="terminal-panel-heading"><h2>인증 후 조회</h2><Link href="/operations">운영·보안 ↗</Link></div>
        <p className="account-muted">웹훅 토큰으로 선물 계정의 읽기 전용 스냅샷을 요청합니다.</p>
        <form onSubmit={lookup}>
          <label>웹훅 토큰<input ref={input} type="password" autoComplete="off" required
            disabled={phase === 'loading'} onChange={event => setHasToken(Boolean(event.target.value.trim()))} /></label>
          <button type="submit" className="account-button account-primary" disabled={!hasToken || phase === 'loading'}>비공개 계정 조회</button>
          {phase !== 'locked' && <button type="button" className="account-button" onClick={clearSnapshot}>
            {phase === 'loading' ? '조회 취소' : '응답 숨기기'}</button>}
        </form>
        {feedback && <p className="account-muted bad" role="alert">{feedback}</p>}
        {phase === 'partial' && <p className="account-muted warn" role="status">응답 일부가 누락되었습니다. 각 데이터 영역의 상태를 확인하세요.</p>}
        <div className="terminal-divider"><h2>거래소 자격증명 보관함</h2>
          <p className={`account-muted ${vaultReady ? 'good' : 'warn'}`}>{vaultNames == null ? '저장 상태 미확인'
            : vaultReady ? 'API 키와 시크릿 저장됨' : 'API 키·시크릿 저장 상태를 확인하세요.'}</p>
        </div>
      </aside>
    </div>
    <Tabs tabs={[
      ['모의투자 계정', <PaperAccount key="paper" paper={paper} />],
      ['미체결 주문', <AccountOrders key="orders" snapshot={snapshot} />],
    ]} />
  </div>
}
