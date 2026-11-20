/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  agentRules: false,
  poweredByHeader: false,
  allowedDevOrigins: ['127.0.0.1', 'localhost'],
}

module.exports = phase => {
  const dev = phase === 'phase-development-server'
  const desktop = process.env.NEXT_PUBLIC_HOYA_DESKTOP === '1'
  const connect = ["'self'"]
  if (!desktop) {
    const api = new URL(process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8010')
    if (['http:', 'https:'].includes(api.protocol)) connect.push(api.origin)
  }
  const policy = [
    "default-src 'self'", "object-src 'none'", "base-uri 'none'", "frame-ancestors 'none'",
    "form-action 'self'", "frame-src 'none'", "img-src 'self' data:", "font-src 'self'",
    "style-src 'self' 'unsafe-inline'", `script-src 'self' 'unsafe-inline'${dev ? " 'unsafe-eval'" : ''}`,
    `connect-src ${connect.join(' ')}`,
  ].join('; ')

  return {
    ...nextConfig,
    distDir: dev ? '.next-dev' : '.next',
    async headers() {
      return [{ source: '/:path*', headers: [
        { key: 'Content-Security-Policy', value: policy },
        { key: 'X-Content-Type-Options', value: 'nosniff' },
        { key: 'X-Frame-Options', value: 'DENY' },
        { key: 'Referrer-Policy', value: 'no-referrer' },
        { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
      ] }]
    },
  }
}
