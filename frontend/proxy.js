import { randomBytes } from 'node:crypto'
import { NextResponse } from 'next/server'

export function proxy(request) {
  const nonce = randomBytes(16).toString('base64')
  const dev = process.env.NODE_ENV === 'development'
  const connect = ["'self'"]
  if (process.env.NEXT_PUBLIC_HOYA_DESKTOP !== '1') {
    const api = new URL(process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8010')
    if (['http:', 'https:'].includes(api.protocol)) connect.push(api.origin)
    if (dev) connect.push('ws://127.0.0.1:3001', 'ws://localhost:3001')
  }
  const policy = [
    "default-src 'self'", "object-src 'none'", "base-uri 'none'", "frame-ancestors 'none'",
    "form-action 'self'", "frame-src 'none'", "img-src 'self' data:", "font-src 'self'",
    "style-src 'self' 'unsafe-inline'", `script-src 'self' 'nonce-${nonce}'${dev ? " 'unsafe-eval'" : ''}`,
    `connect-src ${connect.join(' ')}`,
  ].join('; ')
  const headers = new Headers(request.headers)
  headers.set('Content-Security-Policy', policy)
  const response = NextResponse.next({ request: { headers } })
  response.headers.set('Content-Security-Policy', policy)
  return response
}

export const config = { matcher: '/((?!api/|_next/static|_next/image|favicon.ico).*)' }
