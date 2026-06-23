import './globals.css'
import Link from 'next/link'

export const metadata = { title: 'HoyaTradingSW v2.1', description: 'Intel-driven trading platform' }

const navItems = [
  { href: '/', label: 'Dashboard' },
  { href: '/intel', label: 'Market Intel' },
  { href: '/paper', label: 'Paper Trading' },
  { href: '/risk', label: 'Risk Control' },
  { href: '/account', label: 'Account' },
]

export default function RootLayout({ children }) {
  return (
    <html lang="ko">
      <body>
        <div className="layout">
          <aside className="sidebar">
            <div>
              <div className="brand">HoyaTradingSW</div>
              <div className="brand-sub">v2.1 luminous intelligence</div>
            </div>
            <nav className="nav">
              {navItems.map((item) => (
                <Link key={item.href} href={item.href}>{item.label}</Link>
              ))}
            </nav>
            <div className="sidebar-footer">
              <div className="metric-label">Product Focus</div>
              <div style={{fontWeight:800, marginBottom:8}}>Live Intel + ML + Paper Ops</div>
              <div className="metric-note">뉴스/거시/정책 기반 판단을 paper trading 운영 화면과 연결하는 v2.1 콘솔</div>
            </div>
          </aside>
          <main className="main">{children}</main>
        </div>
      </body>
    </html>
  )
}
