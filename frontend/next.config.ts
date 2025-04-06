import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  // ✅ Ignore ESLint during Vercel build (prevents deployment failures)
  eslint: {
    ignoreDuringBuilds: true,
  },
  
  // ✅ Rewrite frontend calls to your backend service
  async rewrites() {
    return [
      {
        source: '/business-profile',
        destination: 'http://localhost:8000/business-profile',
      },
      {
        source: '/customers',
        destination: 'http://localhost:8000/customers/',
      },
      {
        source: '/sms-style',
        destination: 'http://localhost:8000/sms-style',
      },
    ]
  },
}

export default nextConfig
