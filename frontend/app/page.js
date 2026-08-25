import { fetchJson } from '../lib/api'
import { koBias, koFallback, koPosition, koStrategy, koTopic } from '../lib/ko'

function fmt(n, suffix = '') {
  if (n === null || n === undefined || n === '') return '-'
  const v = Number(n)
  return `${v.toFixed(2)}${suffix}`
}

function buildRiskChip(risk){
  const futures = risk?.risk_guard?.futures || {}
  if (futures.enabled === false) return { label: '보호 정책 꺼짐', className: 'bad' }
  if (futures.max_leverage && Number(futures.max_leverage) <= 5) return { label: '엄격한 보호 정책', className: 'warn' }
  return { label: '보호 정책 작동 중', className: 'good' }
}

export default async function Page() {
  let overview = null, paper = null, risk = null
  const responses = await Promise.allSettled([
    fetchJson('/api/overview'), fetchJson('/api/paper'), fetchJson('/api/risk'),
  ])
  if (responses[0].status === 'fulfilled') overview = responses[0].value
  if (responses[1].status === 'fulfilled') paper = responses[1].value
  if (responses[2].status === 'fulfilled') risk = responses[2].value

  const s = overview?.summary || {}
  const b = overview?.market_brief || {}
  const m = paper?.metrics || {}
  const ml = overview?.ml_signal || {}
  const d = ml?.decision || {}
  const top = b.top || []
  const pnlClass = Number(m.realized_pnl || s.realized_pnl || 0) >= 0 ? 'good' : 'bad'
  const riskChip = buildRiskChip(risk)

  return (
    <>
      <div className="topbar">
        <div>
          <div className="topbar-title">시장 인텔리전스 대시보드</div>
          <div className="topbar-sub">시장 정보, ML 보조 판단, 모의투자 상태를 하나의 제어 화면에서 관리</div>
        </div>
        <div className="chip good">종합 방향 · {koBias(d.bias || b.bias)}</div>
      </div>

      <h1 className="page-title">대시보드</h1>
      <p className="page-sub">실시간 시장 정보를 우선으로 두고 ML 보조 점수와 모의투자 운영 현황을 연결합니다.</p>

      <div className="grid">
        <div className="card span-3 emphasis"><div className="metric-label">모의투자 잔액</div><div className="metric-value mono">${fmt(m.virtual_balance)}</div><div className="metric-note">시작 잔액 대비 현재 가상 잔고</div></div>
        <div className="card span-3"><div className="metric-label">누적 실현 손익</div><div className={`metric-value mono ${pnlClass}`}>${fmt(m.realized_pnl || s.realized_pnl)}</div><div className="metric-note">확정된 거래 손익 기준</div></div>
        <div className="card span-3"><div className="metric-label">누적 수익률</div><div className="metric-value mono">{fmt(m.return_pct || s.return_pct, '%')}</div><div className="metric-note">시작 잔액 대비 성과</div></div>
        <div className="card span-3"><div className="metric-label">시장 방향</div><div className="metric-value">{koBias(d.bias || b.bias)}</div><div className="metric-note">ML과 실시간 시장 정보의 종합 판단</div></div>

        <div className="card span-7 emphasis">
          <div className="split">
            <div>
              <div className="metric-label">핵심 판단</div>
              <div className="metric-value">{koBias(d.bias)}</div>
              <p className="section-sub">실시간 시장 정보와 ML 보조 판단, 대체 정책 상태를 함께 보여줍니다.</p>
            </div>
            <div className="mini-grid" style={{minWidth:280}}>
              <div className="card soft"><div className="metric-label">ML 상승 점수</div><div className="metric-value good mono">{fmt(ml?.scores?.long_score)}</div></div>
              <div className="card soft"><div className="metric-label">ML 하락 점수</div><div className="metric-value bad mono">{fmt(ml?.scores?.short_score)}</div></div>
              <div className="card soft"><div className="metric-label">뉴스 상승 점수</div><div className="metric-value good mono">{fmt(b.long_score)}</div></div>
              <div className="card soft"><div className="metric-label">뉴스 하락 점수</div><div className="metric-value bad mono">{fmt(b.short_score)}</div></div>
            </div>
          </div>
          <div style={{marginTop:18}}>
            <div className="split">
              <span className="metric-note">대체 전략 상태</span>
              <span className="chip warn">{koFallback(paper?.fallback_mode)}</span>
            </div>
            <div className="progress" style={{marginTop:10}}><span style={{width:`${Math.min(100, Math.max(8, Number(d.strength || 0) * 100))}%`}} /></div>
          </div>
        </div>

        <div className="card span-5">
          <div className="section-title">모의투자 현황</div>
          <div className="mini-grid">
            <div><div className="metric-label">상태</div><div className="metric-value">{paper?.running ? '운용 중' : (paper?.paused ? '일시정지' : '중지')}</div></div>
            <div><div className="metric-label">실행 전략</div><div className="metric-value" style={{fontSize:22}}>{koStrategy(paper?.executed_strategy)}</div></div>
            <div><div className="metric-label">시간 단위</div><div className="metric-value" style={{fontSize:22}}>{paper?.executed_timeframe || '-'}</div></div>
            <div><div className="metric-label">포지션 방식</div><div className="metric-value" style={{fontSize:22}}>{koPosition(paper?.executed_position_mode)}</div></div>
          </div>
          <div style={{marginTop:16}} className="metric-note">고정 투자 대상, 1배 매수·현금 정책과 운영 상태를 함께 표시합니다.</div>
        </div>

        <div className="card span-8">
          <div className="section-title">시장 뉴스 미리보기</div>
          <div className="section-sub">한국어 번역 제목을 우선 표시하며 원문은 분석 기준으로 보존합니다.</div>
          {top.slice(0, 6).map((item, idx) => (
            <div key={idx} className="feed-item">
              <div className="split">
                <div>
                  <div style={{fontWeight:700, marginBottom:6}}>{item.title_ko || item.title || '-'}</div>
                  {item.title_ko && item.title_ko !== item.title ? <div className="metric-note" style={{marginBottom:5}}>{item.title}</div> : null}
                  <div className="metric-note">{item.source || '-'} · {koTopic(item.topic)} · {item.event_time || item.published || '-'}</div>
                </div>
                <div style={{display:'flex', gap:8}}>
                  <span className="chip good">상승 {fmt(item.long_event_score)}</span>
                  <span className="chip bad">하락 {fmt(item.short_event_score)}</span>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="card span-4">
          <div className="section-title">위험 관리 현황</div>
          <div className="metric-label">기록된 주문</div>
          <div className="metric-value mono">{s.total_trades || 0}</div>
          <div className="section-sub">성과 기록의 주문 수이며 현재 포지션 수와 구분됩니다. 세부 정책은 위험 관리 화면에서 확인합니다.</div>
          <div className={`chip ${riskChip.className}`}>{riskChip.label}</div>
        </div>

        <div className="card span-12">
          <div className="section-title">제품 설명</div>
          <div className="section-sub">v2.1은 뉴스·거시·정책 이벤트와 ML 신호를 검증 전까지 관찰 모드로 유지하고, 검증된 4시간봉 전략을 모의투자 및 제한된 실거래 안전 제어와 연결합니다.</div>
        </div>
      </div>
    </>
  )
}
