/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  agentRules: false,
  allowedDevOrigins: ['127.0.0.1', 'localhost'],
}
module.exports = phase => ({
  ...nextConfig,
  distDir: phase === 'phase-development-server' ? '.next-dev' : '.next',
})
