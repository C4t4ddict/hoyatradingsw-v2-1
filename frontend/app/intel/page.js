import { fetchJson } from '../../lib/api'
import { koBias, koTopic } from '../../lib/ko'

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

function fmt(n){ return Number(n || 0).toFixed(2) }

function koReadiness(status='collecting'){
  return ({ready:'사용 가능', needs_training:'학습 필요', collecting:'데이터 수집 중', blocked:'점검 필요'})[status] || status
}

function koTarget(target=''){
  const match = target.match(/^label_(up|down)_(.+)$/)
  if(!match) return target
  const horizon = ({'5m':'5분','15m':'15분','30m':'30분','1h':'1시간','4h':'4시간','24h':'24시간'})[match[2]] || match[2]
  return `${horizon} ${match[1] === 'up' ? '상승' : '하락'}`
}

function NewsTitle({item}){
  if(!item) return '-'
  return <><div>{item.title_ko || item.title || '-'}</div>{item.title_ko && item.title_ko !== item.title ? <div className="metric-note" style={{marginTop:6}}>{item.title}</div> : null}</>
}

export default async function IntelPage(){
  let data = null
  try { data = await fetchJson('/api/intel') } catch {}
  const b = data?.market_brief || {}
  const rows = b.top || []
  const ml = data?.ml_signal || {}
  const s = ml?.scores || {}
  const d = ml?.decision || {}
  const quality = data?.signal_quality || ml?.quality_policy || {}
  const qualityWeights = quality?.weights || {}
  const intelQuality = quality?.intel_quality || {}
  const mlQuality = quality?.ml_quality || {}
  const collection = b.collection_status || {}
  const readiness = data?.ml_readiness || {}
  const readinessDataset = readiness.dataset || {}
  const readinessModels = readiness.models || {}
  const readinessTargets = readiness.targets || []
  const bestLong = [...rows].sort((a,b)=>(b.long_event_score||0)-(a.long_event_score||0))[0]
  const bestShort = [...rows].sort((a,b)=>(b.short_event_score||0)-(a.short_event_score||0))[0]

  return (<>
    <div className="topbar">
      <div>
        <div className="topbar-title">시장 인텔리전스</div>
        <div className="topbar-sub">실시간 이벤트를 상승·하락 영향과 신뢰도 관점으로 해석합니다.</div>
      </div>
      <div className="chip good">종합 방향 · {koBias(d.bias || b.bias)}</div>
    </div>

    <h1 className="page-title">시장 인텔리전스</h1>
    <p className="page-sub">뉴스·거시·정책·지정학 이벤트를 스캔하고 ML 보조 판단과 함께 시장 방향성을 읽는 화면</p>

    <div className="grid">
      <div className="card span-3 emphasis"><div className="metric-label">실시간 정보 방향</div><div className="metric-value">{koBias(b.bias)}</div><div className="metric-note">실시간 이벤트 기반 종합 판단</div></div>
      <div className="card span-3"><div className="metric-label">뉴스 상승 점수</div><div className="metric-value mono good">{fmt(b.long_score)}</div><div className="metric-note">상승 영향 합계</div></div>
      <div className="card span-3"><div className="metric-label">뉴스 하락 점수</div><div className="metric-value mono bad">{fmt(b.short_score)}</div><div className="metric-note">하락 영향 합계</div></div>
      <div className="card span-3"><div className="metric-label">ML 방향</div><div className="metric-value">{koBias(d.bias)}</div><div className="metric-note">ML은 보조 판단으로만 사용</div></div>

      <div className="card span-4">
        <div className="section-title">상승 영향 주요 뉴스</div>
        <div className="section-sub">상승 점수가 가장 높은 이벤트</div>
        <div style={{fontWeight:800, marginBottom:8}}><NewsTitle item={bestLong} /></div>
        <div className="metric-note">{bestLong ? `${shortSource(bestLong.source)} · ${koTopic(bestLong.topic)}` : '-'}</div>
        <div style={{marginTop:14}} className="chip good">상승 {fmt(bestLong?.long_event_score)}</div>
      </div>

      <div className="card span-12">
        <div className="split">
          <div>
            <div className="section-title">신호 품질 검증</div>
            <div className="section-sub">실현 결과가 충분히 쌓이고 정확도·보정 기준을 통과한 신호만 실제 판단에 반영한다.</div>
          </div>
          <div className={`chip ${quality.signals_enabled ? 'good' : 'warn'}`}>{quality.signals_enabled ? '검증 완료' : '관찰 모드'}</div>
        </div>
        <div className="mini-grid" style={{marginTop:14}}>
          <div><div className="metric-label">시장 정보 비중</div><div className="metric-value mono" style={{fontSize:22}}>{fmt(Number(qualityWeights.intel||0)*100)}%</div><div className="metric-note">관측 {intelQuality.observations||0}건 · Brier {fmt(intelQuality.brier_score)}</div></div>
          <div><div className="metric-label">ML 비중</div><div className="metric-value mono" style={{fontSize:22}}>{fmt(Number(qualityWeights.ml||0)*100)}%</div><div className="metric-note">관측 {mlQuality.observations||0}건 · Brier {fmt(mlQuality.brier_score)}</div></div>
          <div><div className="metric-label">포지션 배수</div><div className="metric-value mono" style={{fontSize:22}}>{fmt(Number(d.position_size_multiplier||0)*100)}%</div><div className="metric-note">시장 국면을 반영한 허용 노출</div></div>
          <div><div className="metric-label">판단 근거</div><div className="metric-value" style={{fontSize:22}}>{d.trigger_source==='quality_gate'?'품질 검증':(d.trigger_source||'-')}</div><div className="metric-note">검증 전에는 자동으로 중립 유지</div></div>
        </div>
      </div>

      <div className="card span-12">
        <div className="split">
          <div>
            <div className="section-title">ML 학습 준비 상태</div>
            <div className="section-sub">시점 누수·중복·결측·라벨 균형과 시간순 검증을 모두 통과한 모델만 신호에 사용합니다.</div>
          </div>
          <div className={`chip ${readiness.inference_ready ? 'good' : 'warn'}`}>{koReadiness(readiness.status)}</div>
        </div>
        <div className="mini-grid" style={{marginTop:14}}>
          <div><div className="metric-label">데이터 관측치</div><div className="metric-value mono" style={{fontSize:22}}>{readinessDataset.rows ?? 0}</div><div className="metric-note">최소 {readiness.thresholds?.minimum_rows ?? 200}건 필요</div></div>
          <div><div className="metric-label">검증 모델</div><div className="metric-value mono" style={{fontSize:22}}>{readinessModels.validated ?? 0} / {readinessModels.required ?? 12}</div><div className="metric-note">시간순 홀드아웃과 기준 모델 비교</div></div>
          <div><div className="metric-label">중복 이벤트</div><div className="metric-value mono" style={{fontSize:22}}>{readinessDataset.duplicate_events ?? 0}</div><div className="metric-note">동일 이벤트 중복 학습 방지</div></div>
          <div><div className="metric-label">시점 누수 행</div><div className={`metric-value mono ${(readinessDataset.feature_leakage_rows||0) > 0 ? 'bad' : 'good'}`} style={{fontSize:22}}>{readinessDataset.feature_leakage_rows ?? 0}</div><div className="metric-note">뉴스 이후 정보를 입력에 사용한 행</div></div>
        </div>
        {(readiness.blockers||[]).length > 0 ? <div className="inline-error" style={{marginTop:16}}>
          <strong>현재 차단 사유</strong>
          <ul style={{marginBottom:0}}>{readiness.blockers.slice(0,6).map((reason,index)=><li key={index}>{reason}</li>)}</ul>
        </div> : null}
        {readinessTargets.length > 0 ? <div className="table-scroll" style={{marginTop:18}}>
          <table className="table">
            <thead><tr><th>예측 구간</th><th>라벨 수</th><th>상승/하락 사건</th><th>데이터</th><th>모델 검증</th></tr></thead>
            <tbody>{readinessTargets.map((target)=><tr key={target.target}>
              <td>{koTarget(target.target)}</td>
              <td className="mono">{target.rows}</td>
              <td className="mono">{target.positives} / {target.negatives}</td>
              <td><span className={`chip ${target.data_ready ? 'good' : 'warn'}`}>{target.data_ready ? '충족' : '부족'}</span></td>
              <td><span className={`chip ${target.model_validated ? 'good' : 'warn'}`}>{target.model_validated ? '통과' : '대기'}</span></td>
            </tr>)}</tbody>
          </table>
        </div> : null}
      </div>

      <div className="card span-4">
        <div className="section-title">하락 영향 주요 뉴스</div>
        <div className="section-sub">하락 점수가 가장 높은 이벤트</div>
        <div style={{fontWeight:800, marginBottom:8}}><NewsTitle item={bestShort} /></div>
        <div className="metric-note">{bestShort ? `${shortSource(bestShort.source)} · ${koTopic(bestShort.topic)}` : '-'}</div>
        <div style={{marginTop:14}} className="chip bad">하락 {fmt(bestShort?.short_event_score)}</div>
      </div>

      <div className="card span-4">
        <div className="section-title">ML 확률 묶음</div>
        <div className="mini-grid">
          <div><div className="metric-label">5분 상승 / 하락</div><div className="metric-value mono" style={{fontSize:22}}>{(Number(s.up_5m||0)*100).toFixed(1)} / {(Number(s.down_5m||0)*100).toFixed(1)}</div></div>
          <div><div className="metric-label">1시간 상승 / 하락</div><div className="metric-value mono" style={{fontSize:22}}>{(Number(s.up_1h||0)*100).toFixed(1)} / {(Number(s.down_1h||0)*100).toFixed(1)}</div></div>
          <div><div className="metric-label">4시간 상승 / 하락</div><div className="metric-value mono" style={{fontSize:22}}>{(Number(s.up_4h||0)*100).toFixed(1)} / {(Number(s.down_4h||0)*100).toFixed(1)}</div></div>
          <div><div className="metric-label">24시간 상승 / 하락</div><div className="metric-value mono" style={{fontSize:22}}>{(Number(s.up_24h||0)*100).toFixed(1)} / {(Number(s.down_24h||0)*100).toFixed(1)}</div></div>
        </div>
      </div>

      <div className="card span-12">
        <div className="split">
          <div>
            <div className="section-title">수집 상태</div>
            <div className="section-sub">외부 RSS 장애 시에도 성공한 소스 또는 기존 캐시로 즉시 대체</div>
          </div>
          <div className={`chip ${b.stale ? 'warn' : 'good'}`}>{b.stale ? '오래된 캐시' : '실시간 / 캐시'}</div>
        </div>
        <div className="mini-grid" style={{marginTop:14}}>
          <div><div className="metric-label">완료한 출처</div><div className="metric-value mono" style={{fontSize:22}}>{collection.completed ?? '-'}</div></div>
          <div><div className="metric-label">시간 초과</div><div className="metric-value mono" style={{fontSize:22}}>{(collection.timed_out||[]).length}</div></div>
          <div><div className="metric-label">실패</div><div className="metric-value mono" style={{fontSize:22}}>{(collection.failed||[]).length}</div></div>
          <div><div className="metric-label">소요 시간</div><div className="metric-value mono" style={{fontSize:22}}>{collection.elapsed_ms ?? '-'} ms</div></div>
        </div>
      </div>

      <div className="card span-12">
        <div className="split" style={{marginBottom:12}}>
          <div>
            <div className="section-title">시장 뉴스 피드</div>
            <div className="section-sub">날짜·출처·주제·상승/하락 점수와 한국어 번역 제목을 함께 제공합니다.</div>
          </div>
          <div className="metric-note">번역 실패 시 원문을 표시하며 분석은 항상 원문 기준입니다.</div>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>날짜</th><th>출처</th><th>주제</th><th>상승</th><th>하락</th><th>뉴스 제목</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0,12).map((r,i)=><tr key={i}>
              <td className="mono">{fmtDate(r.event_time || r.published)}</td>
              <td>{shortSource(r.source)}</td>
              <td>{koTopic(r.topic)}</td>
              <td className="good mono">{fmt(r.long_event_score)}</td>
              <td className="bad mono">{fmt(r.short_event_score)}</td>
              <td><NewsTitle item={r} /></td>
            </tr>)}
          </tbody>
        </table>
      </div>
    </div>
  </>)
}
