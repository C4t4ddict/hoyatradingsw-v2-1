const BASE = 'http://127.0.0.1:8010'
export async function fetchJson(path){
  const r = await fetch(`${BASE}${path}`, { cache: 'no-store' })
  if(!r.ok) throw new Error(`fetch failed: ${path}`)
  return r.json()
}
