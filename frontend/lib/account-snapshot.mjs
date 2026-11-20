function amount(value) {
  if (typeof value !== 'number' && typeof value !== 'string') return null
  if (typeof value === 'string' && !value.trim()) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

export function accountSnapshot(payload) {
  if (payload?.ok !== true) return null
  const source = payload.balance_error ? null : payload.balance
  const balance = source ? {
    total: amount(source.usdt_total), free: amount(source.usdt_free), used: amount(source.usdt_used),
  } : null
  const positions = !payload.positions_error && Array.isArray(payload.positions) ? payload.positions : null
  const orders = !payload.open_orders_error && Array.isArray(payload.open_orders) ? payload.open_orders : null
  const pnls = positions?.map(row => amount(row.unrealizedPnl))
  const parts = {
    balance: Boolean(balance && Object.values(balance).some(value => value != null)),
    positions: positions != null,
    orders: orders != null,
  }
  return {
    balance, positions, orders, parts,
    pnl: pnls?.every(value => value != null) ? pnls.reduce((total, value) => total + value, 0) : null,
    received: Object.values(parts).filter(Boolean).length,
    complete: parts.positions && parts.orders && Boolean(balance && Object.values(balance).every(value => value != null)),
  }
}
