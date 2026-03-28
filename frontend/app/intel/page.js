import { fetchJson } from '../../lib/api'

export default async function IntelPage(){
  let data = null
  try { data = await fetchJson('/api/intel') } catch {}
  const b = data?.market_brief || {}
  const rows = b.top || []
  const ml = data?.ml_pred || {}
  const p5 = ml?.label_up_5m?.proba?.[1] || 0
  const p15 = ml?.label_up_15m?.proba?.[1] || 0
  const p1 = ml?.label_up_1h?.proba?.[1] || 0
  const p4 = ml?.label_up_4h?.proba?.[1] || 0
  const p24 = ml?.label_up_24h?.proba?.[1] || 0
  return (<><h1 className="page-title">시장 인텔리전스</h1><p className="page-sub">뉴스 / 거시경제 / 국제정세 / ML 예측 통합</p><div className="grid"><div className="card span-3"><div className="metric-label">종합점수</div><div className="metric-value">{Number(b.score || 0).toFixed(2)}</div></div><div className="card span-3"><div className="metric-label">최종 시그널</div><div className="metric-value">{b.signal || '중립'}</div></div><div className="card span-3"><div className="metric-label">트럼프 이슈</div><div className="metric-value">{b.count_trump || 0}</div></div><div className="card span-3"><div className="metric-label">예정 발표</div><div className="metric-value">{b.count_scheduled || 0}</div></div><div className="card span-12"><div className="section-title">ML 예측 확률</div><div className="grid"><div className="card span-3"><div className="metric-label">5m</div><div className="metric-value">{(p5*100).toFixed(1)}%</div></div><div className="card span-3"><div className="metric-label">15m</div><div className="metric-value">{(p15*100).toFixed(1)}%</div></div><div className="card span-2"><div className="metric-label">1h</div><div className="metric-value">{(p1*100).toFixed(1)}%</div></div><div className="card span-2"><div className="metric-label">4h</div><div className="metric-value">{(p4*100).toFixed(1)}%</div></div><div className="card span-2"><div className="metric-label">24h</div><div className="metric-value">{(p24*100).toFixed(1)}%</div></div></div></div><div className="card span-12"><div className="section-title">상위 이벤트</div><table className="table"><thead><tr><th>출처</th><th>토픽</th><th>점수</th><th>제목</th></tr></thead><tbody>{rows.slice(0,10).map((r,i)=><tr key={i}><td>{r.source}</td><td>{r.topic}</td><td>{Number(r.score||0).toFixed(2)}</td><td>{r.title}</td></tr>)}</tbody></table></div></div></>) }
