const BIAS = { neutral:'중립', bullish:'상승', bearish:'하락', long:'상승', lean_long:'상승 우세', short:'하락', lean_short:'하락 우세' }
const STATUS = { active:'활성', resolved:'해제', warning:'주의', critical:'위험', info:'정보', pending:'대기', filled:'체결', rejected:'거부', cancelled:'취소' }
const STRATEGY = { vol_target_momentum:'변동성 목표 모멘텀', trend_continuation_system:'추세 추종', hold:'관망', rsi_reversion:'RSI 평균회귀', breakout_20:'20봉 돌파' }
const POSITION = { long_cash:'매수·현금', long:'매수', short:'매도', flat:'현금', cash:'현금' }
const FALLBACK = { inactive:'비활성', neutral_wait_quality_gate:'중립·품질 검증 대기', cooldown_after_losses:'연속 손실 휴식', runtime_mismatch_hold:'설정 불일치로 관망', neutral_wait_strict:'중립 관망' }
const TOPIC = { crypto:'가상자산', macro:'거시경제', geopolitics:'지정학', other:'기타', regulation:'규제', policy:'정책' }
const CATEGORY = { risk:'위험 관리', worker:'작업자', data:'데이터', ledger:'원장', order:'주문', fill:'체결', system:'시스템' }

export function koBias(value='neutral'){ return BIAS[String(value).toLowerCase()] || value || '-' }
export function koStatus(value=''){ return STATUS[String(value).toLowerCase()] || value || '-' }
export function koStrategy(value=''){ return STRATEGY[String(value).toLowerCase()] || value || '-' }
export function koPosition(value=''){ return POSITION[String(value).toLowerCase()] || value || '-' }
export function koFallback(value='inactive'){ return FALLBACK[String(value).toLowerCase()] || value || '-' }
export function koTopic(value=''){ return TOPIC[String(value).toLowerCase()] || value || '-' }
export function koCategory(value=''){ return CATEGORY[String(value).toLowerCase()] || value || '-' }
export function koBoolean(value){ return value ? '사용' : '미사용' }
export function koAlertMessage(value=''){
  const messages={
    'Paper risk policy blocked execution':'모의투자 위험 정책이 주문 실행을 차단했습니다.',
    'Paper worker is not running':'모의투자 작업자가 실행 중이 아닙니다.',
    'Paper data is stale':'모의투자 시장 데이터가 오래되었습니다.',
  }
  return messages[value] || value || '-'
}
