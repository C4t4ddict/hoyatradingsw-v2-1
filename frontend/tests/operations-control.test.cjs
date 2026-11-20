const test = require('node:test')
const assert = require('node:assert/strict')

test('live confirmation is tied to current challenge and rejects expiry, missing credentials and unknown state', async () => {
  const { canConfirmLive } = await import('../lib/operations-control.mjs')
  const expires = '2026-11-20T09:05:00Z'
  const deadline = Date.parse(expires)
  const challenge = { token: 'test-fixture', expires }
  const control = { live_enabled: false, challenge_pending: true, challenge_expires_at: expires }
  assert.equal(canConfirmLive(control, challenge, true, deadline - 1), true)
  assert.equal(canConfirmLive(control, challenge, true, deadline), false)
  assert.equal(canConfirmLive(control, challenge, false, deadline - 1), false)
  assert.equal(canConfirmLive(null, challenge, true, deadline - 1), false)
  assert.equal(canConfirmLive({ ...control, challenge_expires_at: '2026-11-20T09:08:00Z' }, challenge, true, deadline - 1), false)
  assert.equal(canConfirmLive({ ...control, live_enabled: true }, challenge, true, deadline - 1), false)
})
