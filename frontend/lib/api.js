const BASE = 'http://127.0.0.1:8010'
export async function fetchJson(path){
  const r = await fetch(`${BASE}${path}`, { cache: 'no-store' })
  if(!r.ok) throw new Error(`fetch failed: ${path}`)
  return r.json()
}

export async function postJson(path, body){
  const r = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const payload = await r.json().catch(() => ({}))
  if(!r.ok) throw new Error(payload.detail || `요청 실패: ${path}`)
  return payload
}
