import './globals.css'
import Link from 'next/link'
export const metadata = { title: 'HoyaTradingSW v2.1', description: 'Intel-driven trading platform' }
export default function RootLayout({ children }) {
  return (<html><body><div className="layout"><aside className="sidebar"><div className="brand">HoyaTradingSW v2.1</div><nav className="nav"><Link href="/">개요</Link><Link href="/paper">모의투자</Link><Link href="/intel">시장 인텔리전스</Link><Link href="/account">실시간 계정</Link><Link href="/risk">리스크 가드</Link></nav></aside><main className="main">{children}</main></div></body></html>)
}
