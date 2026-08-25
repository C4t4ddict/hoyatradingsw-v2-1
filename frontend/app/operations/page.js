'use client'

import { useEffect, useState } from 'react'
import { koAlertMessage, koCategory, koStatus } from '../../lib/ko'

const BASE = 'http://127.0.0.1:8010'
const SECRET_NAMES = [
  'API_KEY','API_SECRET','WEBHOOK_TOKEN','ALERT_TELEGRAM_BOT_TOKEN',
  'ALERT_TELEGRAM_CHAT_ID','PAPER_ALERT_TELEGRAM_BOT_TOKEN','PAPER_ALERT_TELEGRAM_CHAT_ID',
]

function fmtDate(value){
  if(!value) return '-'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toISOString().replace('T',' ').slice(0,19)
}

export default function OperationsPage(){
  const [ops,setOps]=useState(null)
  const [security,setSecurity]=useState(null)
  const [live,setLive]=useState(null)
  const [settingsToken,setSettingsToken]=useState('')
  const [challenge,setChallenge]=useState('')
  const [cap,setCap]=useState(100)
  const [secretName,setSecretName]=useState('API_KEY')
  const [secretValue,setSecretValue]=useState('')
  const [message,setMessage]=useState('')
  const [busy,setBusy]=useState(false)

  const load=async()=>{
    const [opsResponse,securityResponse,liveResponse]=await Promise.all([
      fetch(`${BASE}/api/operations`,{cache:'no-store'}),
      fetch(`${BASE}/api/security/status`,{cache:'no-store'}),
      fetch(`${BASE}/api/live/status`,{cache:'no-store'}),
    ])
    if(!opsResponse.ok||!securityResponse.ok||!liveResponse.ok) throw new Error('운영 API 조회 실패')
    const [opsJson,securityJson,liveJson]=await Promise.all([opsResponse.json(),securityResponse.json(),liveResponse.json()])
    setOps(opsJson); setSecurity(securityJson); setLive(liveJson)
    setCap(liveJson?.control?.max_order_usdt||100)
  }

  useEffect(()=>{ load().catch(error=>setMessage(error.message)) },[])

  const mutate=async(path,body=null,method='POST')=>{
    setBusy(true); setMessage('')
    try{
      const response=await fetch(`${BASE}${path}`,{
        method,
        headers:{'Content-Type':'application/json','X-Settings-Token':settingsToken},
        body:body===null?null:JSON.stringify(body),
      })
      const payload=await response.json().catch(()=>({}))
      if(!response.ok) throw new Error(payload.detail||`요청 실패 (${response.status})`)
      setMessage('요청이 반영되었습니다.')
      await load()
      return payload
    }catch(error){ setMessage(error.message); return null }
    finally{ setBusy(false) }
  }

  const requestChallenge=async()=>{
    const result=await mutate('/api/live/challenge',{confirmation:'I UNDERSTAND LIVE ORDERS'})
    if(result?.challenge_token){ setChallenge(result.challenge_token); setMessage('1차 확인 완료. 5분 안에 2차 확인을 진행하세요.') }
  }
  const confirmLive=async()=>{
    const result=await mutate('/api/live/confirm',{challenge_token:challenge,confirmation:'ENABLE LIVE TRADING',duration_minutes:240})
    if(result?.live_enabled) setChallenge('')
  }
  const storeSecret=async()=>{
    const result=await mutate('/api/security/secrets',{name:secretName,value:secretValue})
    if(result?.stored) setSecretValue('')
  }
  const simpleAction=async(path)=>{
    setBusy(true); setMessage('')
    try{
      const response=await fetch(`${BASE}${path}`,{method:'POST',headers:{'X-Settings-Token':settingsToken}})
      const payload=await response.json().catch(()=>({}))
      if(!response.ok) throw new Error(payload.detail||'요청 실패')
      setMessage(payload.path ? `생성: ${payload.path}` : '요청이 반영되었습니다.')
      await load()
    }catch(error){ setMessage(error.message) }
    finally{ setBusy(false) }
  }

  const control=live?.control||security?.live_control||{}
  const audit=ops?.audit||{}
  const worker=audit?.worker||{}
  const integrity=audit?.ledger_integrity||{}
  const alerts=ops?.alerts||[]
  const history=live?.history||[]
  const events=audit?.recent_events||[]
  const vaultSecrets=security?.vault?.secrets||[]

  return (<>
    <div className="topbar">
      <div><div className="topbar-title">운영·보안</div><div className="topbar-sub">작업자·데이터·원장·경보·실거래 전환을 한 화면에서 감사하고 제어합니다.</div></div>
      <div className={`chip ${control.live_enabled?'bad':'good'}`}>{control.live_enabled?'실거래 활성':'모의투자 보호'}</div>
    </div>

    <h1 className="page-title">운영·보안</h1>
    <p className="page-sub">민감정보는 표시하지 않으며, 실거래는 설정 토큰과 두 번의 명시적 확인을 모두 통과해야 제한 시간 동안만 활성화됩니다.</p>
    {message&&<div className="card soft" style={{marginBottom:18,padding:14}}>{message}</div>}

    <div className="grid">
      <div className="card span-3 emphasis"><div className="metric-label">작업자</div><div className={`metric-value ${worker.alive?'good':'bad'}`}>{worker.alive?'정상':'중지'}</div><div className="metric-note">PID {worker.pid||'-'}</div></div>
      <div className="card span-3"><div className="metric-label">원장 무결성</div><div className={`metric-value ${integrity.ok?'good':'bad'}`}>{integrity.ok?'정상':'실패'}</div><div className="metric-note">이벤트 {integrity.events_checked||0}건 확인</div></div>
      <div className="card span-3"><div className="metric-label">활성 경보</div><div className="metric-value mono">{ops?.active_count||0}</div><div className="metric-note">위험 {ops?.critical_count||0}건</div></div>
      <div className="card span-3"><div className="metric-label">마지막 갱신</div><div className="metric-value mono" style={{fontSize:18}}>{fmtDate(audit.last_update)}</div><div className="metric-note">모의투자 실행 상태</div></div>

      <div className="card span-7">
        <div className="split"><div><div className="section-title">실거래 안전 제어</div><div className="section-sub">기본 모의투자, 5분 인증, 2차 확인, 4시간 자동 만료, 주문 금액 상한을 강제합니다.</div></div><div className={`chip ${control.live_enabled?'bad':'good'}`}>{control.live_enabled?'실거래':'모의투자'}</div></div>
        <div className="mini-grid">
          <div><div className="metric-label">설정 토큰</div><input type="password" value={settingsToken} onChange={event=>setSettingsToken(event.target.value)} placeholder="X-Settings-Token" autoComplete="off" /></div>
          <div><div className="metric-label">최대 주문 USDT</div><input type="number" value={cap} onChange={event=>setCap(event.target.value)} /></div>
          <div><div className="metric-label">실거래 만료</div><div className="metric-note mono">{fmtDate(control.expires_at)}</div></div>
          <div><div className="metric-label">인증 상태</div><div className="metric-note">{challenge?'1차 확인 완료':'미요청'} / {fmtDate(control.challenge_expires_at)}</div></div>
        </div>
        <div className="button-row" style={{marginTop:16}}>
          <button disabled={busy||!settingsToken} onClick={()=>mutate('/api/live/order-cap',{max_order_usdt:Number(cap)})}>상한 저장</button>
          <button disabled={busy||!settingsToken||control.live_enabled} onClick={requestChallenge}>1차 실거래 확인</button>
          <button disabled={busy||!settingsToken||!challenge||control.live_enabled} onClick={confirmLive}>2차 실거래 활성화</button>
          <button disabled={busy||!settingsToken||!control.live_enabled} onClick={()=>mutate('/api/live/disable')}>즉시 모의투자 전환</button>
        </div>
      </div>

      <div className="card span-5">
        <div className="section-title">암호화된 자격증명</div>
        <div className="section-sub">값은 Fernet으로 암호화되며 API와 화면에는 이름/설정 여부만 반환된다.</div>
        <div style={{display:'flex',flexDirection:'column',gap:12}}>
          <select value={secretName} onChange={event=>setSecretName(event.target.value)}>{SECRET_NAMES.map(name=><option key={name} value={name}>{name}</option>)}</select>
          <input type="password" value={secretValue} onChange={event=>setSecretValue(event.target.value)} placeholder="저장할 값 (화면에 재표시되지 않음)" autoComplete="new-password" />
          <div className="button-row"><button disabled={busy||!settingsToken||!secretValue} onClick={storeSecret}>암호화 저장</button></div>
        </div>
        <div style={{marginTop:14,display:'flex',gap:8,flexWrap:'wrap'}}>{vaultSecrets.map(secret=><span key={secret.name} className="chip good">{secret.name} · 저장됨</span>)}</div>
        <div className={`chip ${security?.vault?.encryption_configured?'good':'warn'}`} style={{marginTop:14}}>{security?.vault?.encryption_configured?'마스터 키 준비됨':'마스터 키 필요'}</div>
      </div>

      <div className="card span-12">
        <div className="section-title">운영 작업</div>
        <div className="button-row">
          <button disabled={busy||!settingsToken} onClick={()=>simpleAction('/api/paper/ledger/backup')}>원장 백업</button>
          <button disabled={busy||!settingsToken} onClick={()=>simpleAction('/api/paper/ledger/export')}>CSV 내보내기</button>
          <button disabled={busy||!settingsToken} onClick={()=>simpleAction('/api/operations/daily-report/send')}>일간 리포트 전송</button>
          <button disabled={busy} onClick={()=>load().catch(error=>setMessage(error.message))}>새로고침</button>
        </div>
      </div>

      <div className="card span-12"><div className="section-title">운영 경보</div><table className="table"><thead><tr><th>상태</th><th>심각도</th><th>분류</th><th>마지막 감지</th><th>횟수</th><th>메시지</th></tr></thead><tbody>{alerts.slice(0,30).map(alert=><tr key={alert.alert_id}><td>{koStatus(alert.status)}</td><td className={alert.severity==='critical'?'bad':alert.severity==='warning'?'warn':'good'}>{koStatus(alert.severity)}</td><td>{koCategory(alert.category)}</td><td className="mono">{fmtDate(alert.last_seen_at)}</td><td className="mono">{alert.occurrence_count}</td><td>{koAlertMessage(alert.message)}</td></tr>)}</tbody></table></div>

      <div className="card span-6"><div className="section-title">설정 변경 이력</div><table className="table"><thead><tr><th>시간</th><th>작업자</th><th>작업</th></tr></thead><tbody>{history.slice(0,20).map(row=><tr key={row.sequence}><td className="mono">{fmtDate(row.changed_at)}</td><td>{row.actor}</td><td>{row.action}</td></tr>)}</tbody></table></div>
      <div className="card span-6"><div className="section-title">감사 이벤트 이력</div><table className="table"><thead><tr><th>시간</th><th>유형</th><th>버전</th></tr></thead><tbody>{events.slice(0,20).map(row=><tr key={row.event_id}><td className="mono">{fmtDate(row.occurred_at)}</td><td>{row.event_type}</td><td>{row.strategy_version||'-'}</td></tr>)}</tbody></table></div>
    </div>
  </>)
}
