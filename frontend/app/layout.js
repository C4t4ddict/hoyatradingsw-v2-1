import './globals.css'
import NavClient from './NavClient'

export const metadata = { title: 'HoyaTradingSW v2.1', description: '시장 인텔리전스 기반 자동투자 플랫폼' }


export default function RootLayout({ children }) {
  return (
    <html lang="ko">
      <body>
        <div className="layout">
          <aside className="sidebar">
            <div>
              <div className="brand">HoyaTradingSW</div>
              <div className="brand-sub">v2.1 시장 인텔리전스</div>
            </div>
            <nav className="nav"><NavClient /></nav>
            <div className="sidebar-footer">
              <div className="metric-label">제품 방향</div>
              <div style={{fontWeight:800, marginBottom:8}}>시장 정보 + ML + 모의투자</div>
              <div className="metric-note">뉴스·거시·정책 기반 판단을 모의투자 운영 화면과 연결하는 v2.1 콘솔</div>
            </div>
          </aside>
          <main className="main">{children}</main>
        </div>
      </body>
    </html>
  )
}
