import Link from 'next/link'
import { fetchJson } from '../../lib/api'
import { koFallback, koStrategy } from '../../lib/ko'
import { number, percent, timeLabel } from '../../lib/trading-chart.mjs'
import { DetailTable, MetricStrip, Tabs } from '../terminal/Terminal'
import '../terminal/terminal.css'
import './risk.css'

const POLICY_FIELDS = [
  ['dry_run', '모의 실행 강제'], ['require_idempotency_key', '중복 주문 방지 키 필수'],
  ['live_allowed_tags', '실거래 허용 태그'], ['test_tag_force_dry_run', '테스트 태그 모의 실행'],
  ['auto_select_version', '전략 버전 자동 선택'], ['trading_window_utc', '거래 허용 시간 (UTC)'],
  ['vol_pause_enabled', '급변동 시 주문 제한'], ['vol_lookback_candles', '변동성 관측 봉 수'],
  ['vol_spike_threshold_pct', '급변동 기준', value => percent(value)],
  ['market_intel_filter_enabled', '시장 정보 필터'], ['market_intel_min_score', '시장 정보 점수 하한'],
  ['market_intel_block_bearish', '하락 국면 차단'], ['market_intel_size_up_bullish', '상승 시 주문 크기 배수'],
  ['market_intel_size_down_bearish', '하락 시 주문 크기 배수'], ['market_intel_auto_refresh_sec', '브리핑 갱신 간격 (초)'],
  ['ml_filter_enabled', 'ML 필터'], ['ml_min_up_proba_4h', '4시간 상승 확률 하한', value => percent(value, 100)],
  ['ml_block_low_confidence', '낮은 신뢰도 차단'], ['ml_weight_1h', 'ML 1시간 가중치'], ['ml_weight_4h', 'ML 4시간 가중치'],
  ['ml_weight_24h', 'ML 24시간 가중치'], ['ml_min_composite_score', 'ML 종합 점수 하한'],
  ['ml_min_short_confirm', 'ML 매도 확인 하한'],
]
const REASONS = {
  daily_loss_limit: '일일 손실 한도', drawdown_buy_block: '낙폭에 따른 신규 매수 차단',
  stale_market_data: '시세 지연', kill_switch: '긴급 중지',
}
const onOff = (value, on = '사용', off = '미사용') => value === true ? on : value === false ? off : '미확인'
const multiple = value => value == null ? '—' : `${number(value, 0)}배`
const valueLabel = value => Array.isArray(value) ? value.join(', ') || '없음'
  : typeof value === 'boolean' ? onOff(value) : value ?? '—'

function RiskFacts({ items }) {
  return <dl className="terminal-facts">{items.map(([label, value]) =>
    <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
}

export default async function RiskPage() {
  const [riskResult, paperResult] = await Promise.allSettled([fetchJson('/api/risk'), fetchJson('/api/paper')])
  const risk = riskResult.status === 'fulfilled' ? riskResult.value : null
  const paper = paperResult.status === 'fulfilled' ? paperResult.value : null
  const spot = risk?.risk_guard?.spot
  const futures = risk?.risk_guard?.futures
  const policy = risk?.execution_policy
  const live = policy?.live_control
  const session = paper?.risk_status
  const protection = spot?.enabled === false || futures?.enabled === false ? ['보호 비활성', 'bad']
    : spot?.enabled === true && futures?.enabled === true ? ['보호 사용 중', 'good'] : ['보호 상태 미확인', 'warn']
  const mode = policy?.dry_run === true ? '모의 실행 강제'
    : live?.live_enabled === true ? '실거래 제어 활성' : live?.live_enabled === false ? '모의투자 보호' : '미확인'
  const notices = [...new Set([...(session?.rejected ?? []), ...(session?.data_quality?.errors ?? [])])]
  const limits = [
    ['보호 정책', 'enabled', onOff], ['일일 손실 한도 (USDT)', 'daily_loss_limit_usdt', number],
    ['연속 손실 한도', 'max_consecutive_losses', value => number(value, 0)],
    ['최대 보유 포지션', 'max_open_positions', value => number(value, 0)],
    ['최대 레버리지', 'max_leverage', multiple],
    ['매도 포지션', 'allow_short', value => onOff(value, '허용', '차단')],
  ]

  return <div className="terminal risk-terminal">
    <header className="terminal-header">
      <div><p className="terminal-eyebrow">HOYA / 위험 정책</p><h1>위험 관리</h1></div>
      <div className="terminal-header-actions">
        <span className={`terminal-tag ${protection[1]}`}>{protection[0]}</span>
        <Link className="terminal-link" href="/operations">운영·보안 ↗</Link>
      </div>
    </header>
    <MetricStrip items={[
      ['현물 보호', onOff(spot?.enabled), spot?.enabled ? 'good' : undefined],
      ['선물 보호', onOff(futures?.enabled), futures?.enabled ? 'good' : undefined],
      ['선물 최대 레버리지', multiple(futures?.max_leverage)],
      ['주문 실행 모드', mode, mode === '실거래 제어 활성' ? 'warn' : undefined],
      ['모의투자 현재 낙폭', percent(session?.drawdown_pct, 100)],
    ]} />
    <div className="terminal-workspace">
      <section className="terminal-panel">
        <div className="risk-panel-heading terminal-panel-heading"><h2>시장별 주문 보호 한도</h2><span className="terminal-tag">현물 / 선물</span></div>
        <DetailTable columns={['보호 항목', '현물', 'USDT 무기한 선물']} empty="주문 보호 정책을 조회하지 못했습니다."
          rows={risk ? limits.map(([label, key, format]) => ({ id: key, cells: [label, format(spot?.[key]), format(futures?.[key])] })) : []} />
        <p className="terminal-summary">주문 서버에 설정된 한도입니다. 모의투자 세션 한도는 오른쪽에서 확인할 수 있습니다.</p>
      </section>
      <aside className="terminal-panel terminal-context" aria-label="모의투자 위험 요약">
        <div className="terminal-panel-heading"><h2>모의투자 위험 요약</h2><Link href="/paper">모의투자 ↗</Link></div>
        <RiskFacts items={[
          ['일일 손실 한도', percent(paper?.daily_loss_limit_pct, 100)],
          ['대기 주문', number(session?.pending_count, 0)],
          ['시세 품질', onOff(session?.data_quality?.ok, '정상', '차단')],
          ['세션 갱신 (KST)', timeLabel(paper?.last_update)],
        ]} />
        <div className="terminal-divider"><h2>차단·점검 사유</h2>
          {notices.length ? <ul className="risk-notices warn">{notices.map(reason => <li key={reason}>{REASONS[reason] || reason}</li>)}</ul>
            : <p className="risk-muted">{session ? '기록된 차단 사유 없음' : '세션 위험 상태 미확인'}</p>}
        </div>
      </aside>
    </div>
    <Tabs tabs={[
      ['주문 실행 정책', <div key="execution">
        <div className="terminal-summary"><span>실거래 제어 {onOff(live?.live_enabled, '활성', '잠김')}</span>
          <span>건당 주문 상한 {number(live?.max_order_usdt)} USDT</span><span>실거래 만료 (KST) {timeLabel(live?.expires_at)}</span></div>
        <DetailTable columns={['실행 조건', '설정값']} empty="주문 실행 정책을 조회하지 못했습니다."
          rows={policy ? POLICY_FIELDS.map(([key, name, format = valueLabel]) => ({ id: key, cells: [name, format(policy[key])] })) : []} />
      </div>],
      ['모의투자 진단', <div key="paper" className="terminal-context">
        <RiskFacts items={[
          ['실행 전략', koStrategy(paper?.executed_strategy)], ['현재 낙폭', percent(session?.drawdown_pct, 100)],
          ['시세 품질', onOff(session?.data_quality?.ok, '정상', '차단')],
          ['필요 완료 봉', number(session?.data_quality?.required_bars, 0)],
          ['대체 정책', paper ? koFallback(paper.fallback_mode ?? undefined) : '미확인'],
        ]} />
      </div>],
    ]} />
  </div>
}
