'use client'

import { useEffect, useState } from 'react'
import { koPosition } from '../../lib/ko'

const BASE='http://127.0.0.1:8010'
function fmt(n,suffix=''){ if(n===null||n===undefined||n==='') return '-'; const value=Number(n); return Number.isNaN(value)?'-':`${value.toFixed(2)}${suffix}` }

export default function AccountPage(){
  const [paper,setPaper]=useState(null)
  const [security,setSecurity]=useState(null)
  const [account,setAccount]=useState(null)
  const [webhookToken,setWebhookToken]=useState('')
  const [message,setMessage]=useState('')

  useEffect(()=>{
    Promise.all([
      fetch(`${BASE}/api/paper`,{cache:'no-store'}).then(response=>response.json()),
      fetch(`${BASE}/api/security/status`,{cache:'no-store'}).then(response=>response.json()),
    ]).then(([paperData,securityData])=>{setPaper(paperData);setSecurity(securityData)}).catch(()=>setMessage('상태 API 조회 실패'))
  },[])

  const loadPrivateAccount=async()=>{
    setMessage('')
    const response=await fetch(`${BASE}/api/account?market_type=futures`,{cache:'no-store',headers:{'X-Webhook-Token':webhookToken}})
    const payload=await response.json().catch(()=>({}))
    if(!response.ok){setMessage(payload.detail||'인증된 계정 조회 실패');setAccount(null);return}
    setAccount(payload)
  }

  const balance=account?.balance||{}
  const positions=account?.positions||[]
  const metrics=paper?.metrics||{}
  const totalPnl=positions.reduce((sum,position)=>sum+Number(position.unrealizedPnl||0),0)
  const credentialNames=new Set((security?.vault?.secrets||[]).map(item=>item.name))
  const credentialsReady=credentialNames.has('API_KEY')&&credentialNames.has('API_SECRET')
  const connected=Boolean(account?.ok)&&!account?.balance_error

  return (<>
    <div className="topbar"><div><div className="topbar-title">계정 데이터 경계</div><div className="topbar-sub">모의투자 성과와 인증된 거래소 비공개 응답을 명확히 분리합니다.</div></div><div className={`chip ${connected?'good':'warn'}`}>{connected?'비공개 데이터 연결됨':'비공개 데이터 잠김'}</div></div>
    <h1 className="page-title">계정</h1>
    <p className="page-sub">실거래 계정 데이터는 자동 조회하지 않는다. 암호화 자격증명과 Webhook 인증을 모두 갖춘 경우에만 사용자가 명시적으로 조회한다.</p>
    {message&&<div className="card soft" style={{marginBottom:18,padding:14}}>{message}</div>}

    <div className="grid">
      <div className="card span-3 emphasis"><div className="metric-label">연결 상태</div><div className={`metric-value ${connected?'good':'warn'}`}>{connected?'준비됨':'잠김'}</div><div className="metric-note">비공개 API 응답 기준</div></div>
      <div className="card span-3"><div className="metric-label">USDT 총액</div><div className="metric-value mono">{fmt(balance.usdt_total)}</div><div className="metric-note">미조회 값은 0이 아니라 - 로 표시</div></div>
      <div className="card span-3"><div className="metric-label">보유 포지션</div><div className="metric-value mono">{account?positions.length:'-'}</div><div className="metric-note">인증된 응답의 활성 포지션 수</div></div>
      <div className="card span-3"><div className="metric-label">미실현 손익</div><div className={`metric-value mono ${totalPnl>=0?'good':'bad'}`}>{account?fmt(totalPnl):'-'}</div><div className="metric-note">비공개 포지션의 미실현 손익</div></div>

      <div className="card span-5">
        <div className="section-title">인증 후 조회</div>
        <div className="section-sub">토큰은 브라우저 상태에 저장하지 않고 이 요청의 헤더에만 사용한다. 실제 거래소 테스트는 이 개발 범위에서 수행하지 않는다.</div>
        <div className="metric-label">웹훅 토큰</div>
        <input type="password" value={webhookToken} onChange={event=>setWebhookToken(event.target.value)} placeholder="X-Webhook-Token" autoComplete="off" />
        <div className="button-row" style={{marginTop:14}}><button disabled={!webhookToken} onClick={loadPrivateAccount}>비공개 계정 조회</button></div>
        <div style={{marginTop:14}} className={`chip ${credentialsReady?'good':'warn'}`}>{credentialsReady?'암호화 자격증명 준비됨':'API 자격증명 미저장'}</div>
      </div>

      <div className="card span-7">
        <div className="section-title">모의투자 현황</div>
        <div className="mini-grid">
          <div><div className="metric-label">가상 잔액</div><div className="metric-value mono">${fmt(metrics.virtual_balance)}</div></div>
          <div><div className="metric-label">수익률</div><div className={`metric-value mono ${Number(metrics.return_pct||0)>=0?'good':'bad'}`}>{fmt(metrics.return_pct,'%')}</div></div>
          <div><div className="metric-label">실현 손익</div><div className={`metric-value mono ${Number(metrics.realized_pnl||0)>=0?'good':'bad'}`}>{fmt(metrics.realized_pnl)}</div></div>
          <div><div className="metric-label">세션</div><div className="metric-value" style={{fontSize:24}}>{paper?.running?'운용 중':paper?.paused?'일시정지':'중지'}</div></div>
        </div>
      </div>

      <div className="card span-12"><div className="section-title">인증된 포지션</div><table className="table"><thead><tr><th>종목</th><th>방향</th><th>수량</th><th>진입가</th><th>기준가</th><th>미실현 손익</th></tr></thead><tbody>{positions.slice(0,20).map((position,index)=><tr key={index}><td>{position.symbol||'-'}</td><td>{koPosition(position.side)}</td><td className="mono">{position.contracts??'-'}</td><td className="mono">{fmt(position.entryPrice)}</td><td className="mono">{fmt(position.markPrice)}</td><td className={`mono ${Number(position.unrealizedPnl||0)>=0?'good':'bad'}`}>{fmt(position.unrealizedPnl)}</td></tr>)}</tbody></table></div>
    </div>
  </>)
}
