import { number, percent, timeLabel } from '../../lib/trading-chart.mjs'
import { DetailTable } from '../terminal/Terminal'

export function MarketStatus({ runtime }) {
  return <DetailTable columns={['종목', '완료 4시간봉', '누락', '최신 봉 시작 (KST)', '상태']}
    empty={runtime ? '수집된 종목이 없습니다.' : '수집 상태 미확인'}
    rows={(runtime?.market ?? []).map(row => ({ id: row.symbol, cells: [
      row.symbol, `${number(row.rows, 0)} / ${number(row.required, 0)}`, number(row.missing, 0),
      timeLabel(row.latest_ms), <span key="state" className={row.ready ? 'good' : 'warn'}>
        {row.ready ? '정상' : row.stale ? '시세 지연·대기' : '이력 보충 필요'}</span>,
    ] }))} />
}

export function JobHistory({ runtime }) {
  return <DetailTable columns={['작업', '마지막 성공 (KST)', '연속 실패', '다음 시도 (KST)', '오류']}
    empty={runtime ? '수집 작업이 없습니다.' : '수집 상태 미확인'}
    rows={(runtime?.jobs ?? []).map(job => ({ id: job.name, cells: [
      job.name, job.succeeded ? timeLabel(job.succeeded * 1000) : '—', number(job.failures, 0),
      job.next_run ? timeLabel(job.next_run * 1000) : '—', job.error || '—',
    ] }))} />
}

export function CampaignHistory({ runtime }) {
  const campaign = runtime?.campaigns
  return <>
    <p className="terminal-summary">검토 기준 · 유효 관찰 28일, 청산 60건</p>
    <DetailTable columns={['세션', '상태', '관찰 일수', '청산 수', '누락', '수익률', 'Sharpe', '최대 낙폭', 'PF', '수수료 (USDT)']}
      empty={campaign ? '첫 정상 관측을 기다리고 있습니다.' : '캠페인 상태 미확인'}
      rows={(campaign?.sessions ?? []).map(row => ({ id: row.session_id, cells: [
        row.session_id.slice(0, 12), row.status === 'ready_for_review' ? '검토 가능' : '관찰 중',
        number(row.observed_days), number(row.closed_trades, 0), number(row.gap_intervals, 0),
        percent(row.return_pct), number(row.sharpe), percent(row.max_drawdown_pct), number(row.profit_factor), number(row.fees),
      ] }))} />
    <details className="ops-details"><summary>일별 평가 기록 (UTC)</summary>
      <DetailTable columns={['날짜 (UTC)', '세션', '누적 수익률', 'Sharpe', '청산 수']}
        rows={(campaign?.daily ?? []).map(row => ({ id: row.session + row.day, cells: [
          row.day, row.session.slice(0, 12), percent(row.payload.return_pct), number(row.payload.sharpe), number(row.payload.closed_trades, 0),
        ] }))} />
    </details>
  </>
}
