'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

const navItems = [
  { href: '/', label: '대시보드' },
  { href: '/intel', label: '시장 인텔리전스' },
  { href: '/backtest', label: '백테스트' },
  { href: '/paper', label: '모의투자' },
  { href: '/risk', label: '위험 관리' },
  { href: '/operations', label: '운영·보안' },
  { href: '/account', label: '계정' },
]

export default function NavClient(){
  const pathname = usePathname()
  return navItems.map((item) => {
    const active = pathname === item.href
    return <Link key={item.href} href={item.href} className={active ? 'active' : ''}>{item.label}</Link>
  })
}
