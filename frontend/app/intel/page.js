import { fetchJson } from '../../lib/api'

function shortSource(src=''){
  return src
    .replace('GoogleNews:','GNews:')
    .replace('Federal Reserve Press','Fed')
    .replace('SEC Press','SEC')
    .replace('Cointelegraph','CT')
    .replace('The Block','Block')
}

function fmtDate(v=''){
  if (!v) return '-'
  const d = new Date(v)
  if (isNaN(d.getTime())) return v
  return `${d.getUTCFullYear()}.${String(d.getUTCMonth()+1).padStart(2,'0')}.${String(d.getUTCDate()).padStart(2,'0')} ${String(d.getUTCHours()).padStart(2,'0')}:${String(d.getUTCMinutes()).padStart(2,'0')}`
}

function trTopic(t=''){
  if (t === 'crypto') return 'Crypto'
  if (t === 'macro') return 'Macro'
  if (t === 'geopolitics') return 'Geopolitics'
  if (t === 'other') return 'Other'
  return t || '-'
}

function trTitle(t=''){
  return t
    .replaceAll('Bitcoin', '비트코인')
    .replaceAll('bitcoin', '비트코인')
    .replaceAll('Trump', '트럼프')
    .replaceAll('Iran', '이란')
    .replaceAll('Middle East', '중동')
    .replaceAll('inflation', '인플레이션')
}

function fmt(n){ return Number(n || 0).toFixed(2) }

export default async function IntelPage(){
  let data = null
  try { data = await fetchJson('/api/intel') } catch {}
  const b = data?.market_brief || {}
  const rows = b.top || []
  const ml = data?.ml_signal || {}
  const s = ml?.scores || {}
  const d = ml?.decision || {}
  const bestLong = [...rows].sort((a,b)=>(b.long_event_score||0)-(a.long_event_score||0))[0]
  const bestShort = [...rows].sort((a,b)=>(b.short_event_score||0)-(a.short_event_score||0))[0]

  return (<>
    <div className="topbar">
      <div>
        <div className="topbar-title">Market Intel Console</div>
        <div className="topbar-sub">라이브 이벤트를 long / short 영향과 confidence 관점으로 해석하는 인텔리전스 페이지</div>
      </div>
      <div className="chip good">Aggregate bias · {(d.bias || b.bias || 'neutral').toUpperCase()}</div>
    </div>

    <h1 className="page-title">Market Intel</h1>
    <p className="page-sub">뉴스·거시·정책·지정학 이벤트를 스캔하고 ML 보조 판단과 함께 시장 방향성을 읽는 화면</p>

    <div className="grid">
      <div className="card span-3 emphasis"><div className="metric-label">Live Intel Bias</div><div className="metric-value">{(b.bias || 'neutral').toUpperCase()}</div><div className="metric-note">실시간 이벤트 기반 종합 bias</div></div>
      <div className="card span-3"><div className="metric-label">Live Long Score</div><div className="metric-value mono good">{fmt(b.long_score)}</div><div className="metric-note">bullish influence total</div></div>
      <div className="card span-3"><div className="metric-label">Live Short Score</div><div className="metric-value mono bad">{fmt(b.short_score)}</div><div className="metric-note">bearish influence total</div></div>
      <div className="card span-3"><div className="metric-label">ML Bias</div><div className="metric-value">{(d.bias || 'neutral').toUpperCase()}</div><div className="metric-note">ML은 보조 판단으로 사용</div></div>

      <div className="card span-4">
        <div className="section-title">Bullish Spotlight</div>
        <div className="section-sub">가장 강한 long 이벤트</div>
        <div style={{fontWeight:800, marginBottom:8}}>{bestLong ? trTitle(bestLong.title) : '-'}</div>
        <div className="metric-note">{bestLong ? `${shortSource(bestLong.source)} · ${trTopic(bestLong.topic)}` : '-'}</div>
        <div style={{marginTop:14}} className="chip good">L {fmt(bestLong?.long_event_score)}</div>
      </div>

      <div className="card span-4">
        <div className="section-title">Bearish Spotlight</div>
        <div className="section-sub">가장 강한 short 이벤트</div>
        <div style={{fontWeight:800, marginBottom:8}}>{bestShort ? trTitle(bestShort.title) : '-'}</div>
        <div className="metric-note">{bestShort ? `${shortSource(bestShort.source)} · ${trTopic(bestShort.topic)}` : '-'}</div>
        <div style={{marginTop:14}} className="chip bad">S {fmt(bestShort?.short_event_score)}</div>
      </div>

      <div className="card span-4">
        <div className="section-title">ML Probability Stack</div>
        <div className="mini-grid">
          <div><div className="metric-label">5m Up / Down</div><div className="metric-value mono" style={{fontSize:22}}>{(Number(s.up_5m||0)*100).toFixed(1)} / {(Number(s.down_5m||0)*100).toFixed(1)}</div></div>
          <div><div className="metric-label">1h Up / Down</div><div className="metric-value mono" style={{fontSize:22}}>{(Number(s.up_1h||0)*100).toFixed(1)} / {(Number(s.down_1h||0)*100).toFixed(1)}</div></div>
          <div><div className="metric-label">4h Up / Down</div><div className="metric-value mono" style={{fontSize:22}}>{(Number(s.up_4h||0)*100).toFixed(1)} / {(Number(s.down_4h||0)*100).toFixed(1)}</div></div>
          <div><div className="metric-label">24h Up / Down</div><div className="metric-value mono" style={{fontSize:22}}>{(Number(s.up_24h||0)*100).toFixed(1)} / {(Number(s.down_24h||0)*100).toFixed(1)}</div></div>
        </div>
      </div>

      <div className="card span-12">
        <div className="split" style={{marginBottom:12}}>
          <div>
            <div className="section-title">Intel Feed</div>
            <div className="section-sub">date-first / source / topic / L-S score / translated title 구조 유지</div>
          </div>
          <div style={{display:'flex',gap:8,flexWrap:'wrap'}}>
            <span className="chip">All Sources</span>
            <span className="chip">All Topics</span>
            <span className="chip warn">Recency Weighted</span>
          </div>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>Date</th><th>Source</th><th>Topic</th><th>Long</th><th>Short</th><th>Title</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0,12).map((r,i)=><tr key={i}>
              <td className="mono">{fmtDate(r.event_time || r.published)}</td>
              <td>{shortSource(r.source)}</td>
              <td>{trTopic(r.topic)}</td>
              <td className="good mono">{fmt(r.long_event_score)}</td>
              <td className="bad mono">{fmt(r.short_event_score)}</td>
              <td>{trTitle(r.title)}</td>
            </tr>)}
          </tbody>
        </table>
      </div>
    </div>
  </>)
}
