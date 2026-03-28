'use client'
import { useEffect, useState } from 'react'
const BASE = 'http://127.0.0.1:8010'
export default function PaperPage(){
  const [data,setData]=useState(null)
  const [loading,setLoading]=useState(false)
  const load=async()=>{ const r=await fetch(`${BASE}/api/paper`,{cache:'no-store'}); setData(await r.json()) }
  useEffect(()=>{ load() },[])
  const call=async(path)=>{ setLoading(true); await fetch(`${BASE}${path}`,{method:'POST'}); await load(); setLoading(false) }
  const m=data?.metrics||{}
  return (<><h1 className="page-title">모의투자</h1><p className="page-sub">실전 전 검증을 위한 paper trading 중심 화면</p><div className="grid"><div className="card span-3"><div className="metric-label">상태</div><div className="metric-value">{data?.running ? 'RUN' : (data?.paused ? 'PAUSE':'STOP')}</div></div><div className="card span-3"><div className="metric-label">가상 잔고</div><div className="metric-value">{Number(m.virtual_balance || 0).toFixed(2)}</div></div><div className="card span-3"><div className="metric-label">수익률</div><div className="metric-value">{Number(m.return_pct || 0).toFixed(2)}%</div></div><div className="card span-3"><div className="metric-label">트레이드 수</div><div className="metric-value">{m.trades || 0}</div></div><div className="card span-12"><div className="section-title">제어</div><div style={{display:'flex',gap:12}}><button onClick={()=>call('/api/paper/start')} disabled={loading}>시작</button><button onClick={()=>call('/api/paper/pause')} disabled={loading}>일시정지</button><button onClick={()=>call('/api/paper/reset')} disabled={loading}>리셋</button><button onClick={load} disabled={loading}>새로고침</button></div></div></div></>) }
