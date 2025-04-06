const isProd = process.env.NODE_ENV === "production"

const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/business-profile/:path*",
        destination: isProd
          ? "https://engageai.onrender.com/business-profile/:path*"
          : "http://localhost:8000/business-profile/:path*",
      },
      {
        source: "/customers/:path*",
        destination: isProd
          ? "https://engageai.onrender.com/customers/:path*"
          : "http://localhost:8000/customers/:path*",
      },
      {
        source: "/sms-style/:path*",
        destination: isProd
          ? "https://engageai.onrender.com/sms-style/:path*"
          : "http://localhost:8000/sms-style/:path*",
      },
      {
        source: "/ai_sms/:path*",
        destination: isProd
          ? "https://engageai.onrender.com/ai_sms/:path*"
          : "http://localhost:8000/ai_sms/:path*",
      },
      {
        source: "/review/:path*",
        destination: isProd
          ? "https://engageai.onrender.com/review/:path*"
          : "http://localhost:8000/review/:path*",
      },
      {
        source: "/engagement/:path*",
        destination: isProd
          ? "https://engageai.onrender.com/engagement/:path*"
          : "http://localhost:8000/engagement/:path*",
      },
      {
        source: "/conversations/:path*",
        destination: isProd
          ? "https://engageai.onrender.com/conversations/:path*"
          : "http://localhost:8000/conversations/:path*",
      },
    ]
  },
  eslint: {
    ignoreDuringBuilds: true,
  },
}

export default nextConfig
