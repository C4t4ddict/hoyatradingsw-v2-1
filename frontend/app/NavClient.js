'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

const navItems = [
  { href: '/', label: 'Dashboard' },
  { href: '/intel', label: 'Market Intel' },
  { href: '/paper', label: 'Paper Trading' },
  { href: '/risk', label: 'Risk Control' },
  { href: '/account', label: 'Account' },
]

export default function NavClient(){
  const pathname = usePathname()
  return navItems.map((item) => {
    const active = pathname === item.href
    return <Link key={item.href} href={item.href} className={active ? 'active' : ''}>{item.label}</Link>
  })
}
