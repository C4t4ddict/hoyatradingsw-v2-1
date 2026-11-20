const test = require('node:test')
const assert = require('node:assert/strict')

test('empty positions and zero balance are distinct from private API section failures', async () => {
  const { accountSnapshot } = await import('../lib/account-snapshot.mjs')
  assert.equal(accountSnapshot({ ok: false }), null)
  const valid = accountSnapshot({ ok: true, balance: { usdt_total: 0, usdt_free: '0.00' }, positions: [], open_orders: [] })
  assert.deepEqual(valid.balance, { total: 0, free: 0, used: null })
  assert.equal(valid.pnl, 0)
  assert.equal(valid.received, 3)
  assert.equal(valid.complete, false)
  assert.equal(accountSnapshot({ ok: true, balance: { usdt_total: 0, usdt_free: 0, usdt_used: 0 }, positions: [], open_orders: [] }).complete, true)
  const partial = accountSnapshot({ ok: true, balance_error: 'failed', balance: { usdt_total: 0 },
    positions_error: 'failed', positions: [], open_orders: [] })
  assert.equal(partial.balance, null)
  assert.equal(partial.positions, null)
  assert.equal(partial.pnl, null)
  assert.equal(partial.received, 1)
})

test('positions can be shown without guessing aggregate profit when an amount is missing', async () => {
  const { accountSnapshot } = await import('../lib/account-snapshot.mjs')
  const partial = accountSnapshot({ ok: true, positions: [{ unrealizedPnl: null }, { unrealizedPnl: '1.25' }] })
  assert.equal(partial.positions.length, 2)
  assert.equal(partial.pnl, null)
  assert.equal(accountSnapshot({ ok: true, positions: [{ unrealizedPnl: '-1.25' }, { unrealizedPnl: 2 }] }).pnl, 0.75)
})
