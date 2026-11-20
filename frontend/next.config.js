/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  agentRules: false,
  poweredByHeader: false,
  allowedDevOrigins: ['127.0.0.1', 'localhost'],
}

module.exports = phase => {
  const dev = phase === 'phase-development-server'
  return {
    ...nextConfig,
    distDir: dev ? '.next-dev' : '.next',
    async headers() {
      return [{ source: '/:path*', headers: [
        { key: 'X-Content-Type-Options', value: 'nosniff' },
        { key: 'X-Frame-Options', value: 'DENY' },
        { key: 'Referrer-Policy', value: 'no-referrer' },
        { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
      ] }]
    },
  }
}
