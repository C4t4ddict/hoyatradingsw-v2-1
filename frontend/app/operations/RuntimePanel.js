'use client'

import { useEffect, useState } from 'react'
import { API_BASE } from '../../lib/api'

const date = value => value ? new Date(value).toLocaleString('ko-KR', {timeZone:'UTC'}) + ' UTC' : '-'
const number = value => value === null || value === undefined ? '-' : Number(value).toFixed(2)

export default function RuntimePanel({settingsToken}) {
  const [data,setData] = useState(null)
  const [error,setError] = useState('')
  const [busy,setBusy] = useState(false)
  const load = async signal => {
    const response = await fetch(`${API_BASE}/api/runtime`, {cache:'no-store', signal})
    if (!response.ok) throw new Error('수집·평가 상태를 불러오지 못했습니다.')
    setData(await response.json())
  }
  useEffect(() => {
    const controller = new AbortController()
    const refresh = () => load(controller.signal).then(()=>setError('')).catch(e=>{if(e.name!=='AbortError')setError(e.message)})
    refresh()
    const timer = setInterval(refresh, 15000)
    return () => {clearInterval(timer); controller.abort()}
  }, [])
  const control = async (action, path='/api/runtime/control') => {
    setBusy(true);setError('')
    try {
      const response = await fetch(`${API_BASE}${path}`, {method:'POST',
        headers:{'Content-Type':'application/json','X-Settings-Token':settingsToken},
        body:path.endsWith('/control')?JSON.stringify({action}):undefined})
      const result = await response.json()
      if(!response.ok)throw new Error(result.detail || '작업 실패')
      await load()
    }catch(e){setError(e.message)}finally{setBusy(false)}
  }
  return <section className="card" style={{marginBottom:18}} aria-label="수집과 모의투자 평가">
    <div className="section-title">데이터 수집·모의투자 평가</div>
    <p className="section-sub">15초마다 갱신 · 완료된 4시간봉 · 실제 주문 없는 모의 관측</p>
    {error&&<p role="alert" className="inline-error">{error}</p>}
    {!data?<p>운영 상태를 불러오는 중…</p>:<>
      <div className="button-row" style={{marginBottom:16}}>
        <span className={`chip ${data.worker.alive&&data.worker.enabled?'good':'warn'}`}>
          {data.worker.alive?(data.worker.enabled?'수집기 실행 중':'수집 일시정지'):'수집기 미실행'}
        </span>
        {['resume','pause','retry'].map((action,i)=><button key={action} disabled={busy||!settingsToken} onClick={()=>control(action)}>{['수집 재개','수집 일시정지','실패 작업 재시도'][i]}</button>)}
        <button disabled={busy||!settingsToken} onClick={()=>control(null,'/api/paper/resume')}>기존 모의투자 재개</button>
      </div>
      {!data.worker.alive&&<p className="metric-note">수집기 프로세스가 필요합니다. 개발 실행 스크립트 또는 운영 가이드의 수집기 명령을 실행하세요.</p>}
      <div className="table-scroll"><table className="table"><thead><tr><th>심볼</th><th>완료 봉</th><th>누락</th><th>최신 봉 시작</th><th>사용 가능</th></tr></thead><tbody>
        {data.market.map(row=><tr key={row.symbol}><td>{row.symbol}</td><td>{row.rows}/{row.required}</td><td>{row.missing}</td><td>{date(row.latest_ms)}</td><td className={row.ready?'good':'warn'}>{row.ready?'정상':row.stale?'지연·대기':'백필 필요'}</td></tr>)}
      </tbody></table></div>
      <details><summary>수집 작업 및 오류 ({data.jobs.filter(j=>j.error).length}건)</summary><div className="table-scroll"><table className="table"><thead><tr><th>작업</th><th>최종 성공</th><th>실패 횟수</th><th>다음 시도</th><th>오류</th></tr></thead><tbody>
        {data.jobs.map(j=><tr key={j.name}><td>{j.name}</td><td>{date(j.succeeded*1000)}</td><td>{j.failures}</td><td>{date(j.next_run*1000)}</td><td>{j.error||'-'}</td></tr>)}
      </tbody></table></div></details>
      <h3>모의투자 관찰 캠페인</h3>
      <p className="metric-note">유효 관찰 28일 + 청산 60건을 충족하면 검토 가능 상태가 됩니다. 자동 실거래 승격은 하지 않습니다.</p>
      {!data.campaigns.sessions.length&&<p>첫 정상 모의투자 관측을 기다리고 있습니다.</p>}
      {data.campaigns.sessions.map(c=><div key={c.session_id} className="feed-item">
        <strong>{c.session_id.slice(0,12)} · {c.status==='ready_for_review'?'검토 가능':'관찰 중'}</strong>
        <p>관찰 {number(c.observed_days)}/28일 · 청산 {c.closed_trades}/60건 · 누락 구간 {c.gap_intervals}개</p>
        <p>수익률 {number(c.return_pct)}% · Sharpe {number(c.sharpe)} · 최대 낙폭 {number(c.max_drawdown_pct)}% · PF {number(c.profit_factor)} · 수수료 {number(c.fees)} USDT</p>
      </div>)}
      <details><summary>일별 평가 기록 (UTC)</summary><div className="table-scroll"><table className="table"><thead><tr><th>날짜</th><th>세션</th><th>누적 수익률</th><th>Sharpe</th><th>청산 수</th></tr></thead><tbody>
        {data.campaigns.daily.map(d=><tr key={d.session+d.day}><td>{d.day}</td><td>{d.session.slice(0,12)}</td><td>{number(d.payload.return_pct)}%</td><td>{number(d.payload.sharpe)}</td><td>{d.payload.closed_trades}</td></tr>)}
      </tbody></table></div></details>
      <h3>신호 결과 자동 추적</h3>
      <p className="metric-note">뉴스·전략·ML의 그림자 관측입니다. 순수익은 방향 가격 반응에서 가정 비용을 뺀 값이며 실제 계좌 손익이 아닙니다.</p>
      {data.signals.totals.map(s=><p key={s.kind}>{s.kind}: 대기 {s.pending} · 확정 {s.resolved} · 평균 비용 차감 수익률 {number(s.mean_net_return===null?null:s.mean_net_return*100)}%</p>)}
      {!data.signals.totals.length&&<p>새 신호 수집을 기다리고 있습니다.</p>}
      <details><summary>최근 신호 기록</summary><div className="table-scroll"><table className="table"><thead><tr><th>관측 시각</th><th>유형</th><th>심볼</th><th>기간</th><th>순수익</th></tr></thead><tbody>
        {data.signals.recent.map(s=><tr key={s.id}><td>{date(s.observed_ms)}</td><td>{s.kind}</td><td>{s.symbol}</td><td>{s.horizon}h</td><td>{s.net===null?'만기·가격 대기':number(s.net*100)+'%'}</td></tr>)}
      </tbody></table></div></details>
    </>}
  </section>
}
