export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8010'
const BASE = API_BASE
export async function fetchJson(path){
  const r = await fetch(`${BASE}${path}`, { cache: 'no-store' })
  if(!r.ok) throw new Error(`fetch failed: ${path}`)
  return r.json()
}

export async function postJson(path, body, settingsToken){
  const r = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(settingsToken && { 'X-Settings-Token': settingsToken }) },
    body: JSON.stringify(body),
  })
  const payload = await r.json().catch(() => ({}))
  if(!r.ok) throw new Error(payload.detail || `요청 실패: ${path}`)
  return payload
}
