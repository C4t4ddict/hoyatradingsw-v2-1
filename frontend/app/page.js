import Link from 'next/link'
import { fetchJson } from '../lib/api'
import { eventTime, number, percent, timeLabel } from '../lib/trading-chart.mjs'
import CandleChart from './terminal/CandleChart'
import { DetailTable, MetricStrip, NewsItem, SignalDetails, SignalResults, Tabs } from './terminal/Terminal'
import './terminal/terminal.css'

export default async function Page() {
  const results = await Promise.allSettled(['/api/overview', '/api/paper', '/api/runtime'].map(fetchJson))
  const [overview, paper, runtime] = results.map(result => result.status === 'fulfilled' ? result.value : null)
  const brief = overview?.market_brief
  const news = brief?.top ?? []
  const signals = runtime?.signals
  const jobs = runtime?.jobs ?? []
  const failures = jobs.filter(job => job.error).length
  const worker = runtime?.worker
  const collector = !worker ? '확인 불가' : !worker.enabled ? '일시정지'
    : !worker.alive ? '중단' : failures ? `오류 ${failures}건` : '정상'
  const lastSuccess = Math.max(0, ...jobs.map(job => job.succeeded ?? 0))
  const paperState = !paper ? '확인 불가' : paper.paused ? '일시정지' : paper.running ? '운용 중' : '중지'
  const metrics = paper?.metrics
  const markers = [
    ...news.map(item => ({ time: eventTime(item.event_time), kind: 'news', label: item.title_ko || item.title })),
    ...(signals?.recent ?? []).map(item => ({ time: item.observed_ms, symbol: item.symbol, kind: 'signal',
      label: `${item.direction > 0 ? '상승' : '하락'} 관찰 · ${item.horizon}시간` })),
  ]
  return <div className="terminal">
    <header className="terminal-header">
      <div><p className="terminal-eyebrow">HOYA / 시장</p><h1>트레이딩 대시보드</h1></div>
      <div className="terminal-header-actions">
        <span className={collector === '정상' ? 'terminal-tag good' : 'terminal-tag warn'}>● 수집 {collector}</span>
        <Link className="terminal-link" href="/paper">모의투자 열기 <span aria-hidden="true">↗</span></Link>
      </div>
    </header>
    <MetricStrip items={[
      ['모의투자 상태', paperState, paper?.running && !paper?.paused ? 'good' : undefined],
      ['가상 자산 · USDT', number(metrics?.virtual_balance)],
      ['누적 수익률', percent(metrics?.return_pct), metrics?.return_pct == null ? undefined : metrics.return_pct >= 0 ? 'good' : 'bad'],
      ['일일 손실 한도', percent(paper?.daily_loss_limit_pct, 100)],
      ['최근 수집 성공 (KST)', lastSuccess ? timeLabel(lastSuccess * 1000) : '—'],
    ]} />
    <div className="terminal-workspace">
      <CandleChart markers={markers} />
      <aside aria-label="시장 신호와 뉴스" className="terminal-panel terminal-context">
        <SignalDetails signal={overview?.ml_signal} brief={brief} />
        <div className="terminal-panel-heading terminal-divider"><h2>뉴스 근거</h2><Link href="/intel">전체 보기 ↗</Link></div>
        {news.length ? news.slice(0, 3).map((item, index) => <NewsItem key={item.event_id || index} item={item} />)
          : <p className="terminal-empty">{brief ? '관련 뉴스가 없습니다.' : '뉴스를 불러오지 못했습니다.'}</p>}
      </aside>
    </div>
    <Tabs tabs={[
      ['신호 결과', <SignalResults key="signals" signals={signals} />],
      ['시장 뉴스', <div key="news" className="terminal-news-list">
        {news.length ? news.map((item, index) => <NewsItem key={item.event_id || index} item={item} />)
          : <p className="terminal-empty">{brief ? '관련 뉴스가 없습니다.' : '뉴스를 불러오지 못했습니다.'}</p>}
      </div>],
      ['수집 로그', <DetailTable key="jobs" columns={['작업', '상태', '최근 성공 (KST)', '오류']}
        empty={runtime ? '수집 기록이 없습니다.' : '수집 기록을 불러오지 못했습니다.'}
        rows={jobs.map(job => ({ id: job.name, cells: [
          job.name, job.error ? '오류' : job.succeeded ? '성공' : '대기',
          job.succeeded ? timeLabel(job.succeeded * 1000) : '—', job.error || '—',
        ] }))} />],
    ]} />
  </div>
}
