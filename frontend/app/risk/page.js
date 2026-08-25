import { fetchJson } from '../../lib/api'
import { koBoolean } from '../../lib/ko'

function Row({label, value, className=''}){
  return <tr><td>{label}</td><td className={className}>{String(value ?? '-')}</td></tr>
}

function buildRiskState(spot, futures){
  if (futures.enabled === false || spot.enabled === false) return { label:'보호 정책 꺼짐', className:'bad' }
  if (futures.max_leverage && Number(futures.max_leverage) <= 5) return { label:'엄격한 정책', className:'warn' }
  return { label:'보호 정책 작동 중', className:'good' }
}

const policyLabels={dry_run:'모의 실행',live_control:'실거래 제어',require_idempotency_key:'중복 주문 방지 키 필수',test_tag_force_dry_run:'테스트 태그 모의 실행 강제'}
function policyValue(key,value){
  if(key==='live_control') return value?.live_enabled?'실거래 활성':'모의투자 보호'
  if(typeof value==='boolean') return koBoolean(value)
  return typeof value==='object'?JSON.stringify(value):value
}

export default async function RiskPage(){
  let data=null
  try { data=await fetchJson('/api/risk') } catch {}
  const guards=data?.risk_guard||{}
  const spot=guards.spot||{}
  const futures=guards.futures||{}
  const executionPolicy=data?.execution_policy||{}
  const warnings=[
    !futures.enabled?'선물 위험 보호 정책이 꺼져 있습니다.':null,
    !spot.enabled?'현물 위험 보호 정책이 꺼져 있습니다.':null,
    futures.max_leverage?`최대 레버리지 ${futures.max_leverage}배`:null,
    futures.allow_short===false?'선물 매도 포지션이 차단되어 있습니다.':null,
  ].filter(Boolean)
  const riskState=buildRiskState(spot,futures)

  return (<>
    <div className="topbar"><div><div className="topbar-title">위험 관리 인텔리전스</div><div className="topbar-sub">손실 제한, 연속 손실, 포지션 제한과 실행 정책을 운영 관점에서 보여줍니다.</div></div><div className={`chip ${riskState.className}`}>{riskState.label}</div></div>
    <h1 className="page-title">위험 관리</h1>
    <p className="page-sub">낙폭, 일일 손실, 레버리지, 포지션 한도와 실행 정책을 한 화면에서 확인합니다.</p>

    <div className="grid">
      <div className="card span-3 emphasis"><div className="metric-label">현물 보호</div><div className="metric-value">{spot.enabled?'사용':'미사용'}</div><div className="metric-note">현물 위험 보호 상태</div></div>
      <div className="card span-3"><div className="metric-label">선물 보호</div><div className="metric-value">{futures.enabled?'사용':'미사용'}</div><div className="metric-note">선물 위험 보호 상태</div></div>
      <div className="card span-3"><div className="metric-label">최대 레버리지</div><div className="metric-value mono">{futures.max_leverage??'-'}배</div><div className="metric-note">허용 가능한 최대 배수</div></div>
      <div className="card span-3"><div className="metric-label">매도 정책</div><div className="metric-value">{futures.allow_short?'허용':'차단'}</div><div className="metric-note">선물 매도 포지션 허용 여부</div></div>

      <div className="card span-6"><div className="section-title">현물 위험 한도</div><table className="table"><tbody>
        <Row label="정책 사용" value={koBoolean(spot.enabled)} className={spot.enabled?'good mono':'bad mono'} />
        <Row label="일일 손실 한도 (USDT)" value={spot.daily_loss_limit_usdt} className="mono" />
        <Row label="최대 연속 손실" value={spot.max_consecutive_losses} className="mono" />
        <Row label="최대 보유 포지션" value={spot.max_open_positions} className="mono" />
      </tbody></table></div>

      <div className="card span-6"><div className="section-title">선물 위험 한도</div><table className="table"><tbody>
        <Row label="정책 사용" value={koBoolean(futures.enabled)} className={futures.enabled?'good mono':'bad mono'} />
        <Row label="일일 손실 한도 (USDT)" value={futures.daily_loss_limit_usdt} className="mono" />
        <Row label="최대 연속 손실" value={futures.max_consecutive_losses} className="mono" />
        <Row label="최대 보유 포지션" value={futures.max_open_positions} className="mono" />
        <Row label="최대 레버리지" value={futures.max_leverage} className="mono" />
        <Row label="매도 포지션 허용" value={koBoolean(futures.allow_short)} className={futures.allow_short?'good mono':'bad mono'} />
      </tbody></table></div>

      <div className="card span-4"><div className="section-title">주의 사항</div><div className="section-sub">현재 실행 정책에서 확인할 항목입니다.</div><div style={{display:'flex',flexDirection:'column',gap:10}}>{warnings.length?warnings.map((warning,index)=><div key={index} className="chip warn">{warning}</div>):<div className="chip good">현재 정책이 안정적으로 적용 중입니다.</div>}</div></div>

      <div className="card span-8"><div className="section-title">실행 정책</div><div className="section-sub">현재 백엔드가 강제하는 주문 실행 정책입니다.</div><table className="table"><tbody>{Object.entries(executionPolicy).map(([key,value])=><Row key={key} label={policyLabels[key]||key} value={policyValue(key,value)} className="mono" />)}</tbody></table></div>

      <div className="card span-12"><div className="section-title">위험 관리 설명</div><div className="section-sub">일일 손실, 연속 손실, 레버리지, 매도 허용 여부와 실행 정책을 함께 보여줘 운용 안정성을 빠르게 판단하도록 설계했습니다.</div></div>
    </div>
  </>)
}
