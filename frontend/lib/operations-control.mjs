export function canConfirmLive(control, challenge, hasSettingsToken, now = Date.now()) {
  if (!hasSettingsToken || control?.live_enabled !== false || !control.challenge_pending || !challenge?.token) return false
  const deadline = Date.parse(challenge.expires)
  return Number.isFinite(deadline) && deadline === Date.parse(control.challenge_expires_at) && now < deadline
}

export function operationError(status) {
  if (status === 401 || status === 403) return '설정 토큰을 확인하세요.'
  if (status === 503) return '현재 작업을 사용할 수 없습니다. 서버 설정과 수집 상태를 확인하세요.'
  if (status === 400 || status === 409 || status === 422) return '요청 조건을 확인하세요. 값이 유효한지 또는 확인 시간이 만료됐는지 확인할 수 있습니다.'
  return '작업을 완료하지 못했습니다. 상태를 새로고침한 뒤 확인하세요.'
}
