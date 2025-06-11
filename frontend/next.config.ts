//frontend/next.config.ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  eslint: {
    ignoreDuringBuilds: true,
  },
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'images.unsplash.com',
        port: '',
        pathname: '/**', 
      },
    ],
  },
  // --- START MODIFICATION ---
  // The 'rewrites' function is updated to correctly proxy only API calls.
  async rewrites() {
    return [
      {
        // This 'source' now specifically matches paths that start with /api/
        // and proxies them to the backend. This prevents it from interfering
        // with Next.js page routing.
        source: '/api/:path*',
        destination: 'http://localhost:8000/:path*', 
      },
    ];
  },
  // --- END MODIFICATION ---
};

export default nextConfig;
