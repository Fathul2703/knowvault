import type { NextConfig } from "next";

// Where the Next.js server forwards /api/* requests. The browser only ever talks to this
// origin, so session cookies stay first-party and no CORS configuration is needed.
const apiInternalUrl = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // A self-contained server for the production image (apps/web/Dockerfile).
  output: "standalone",
  experimental: {
    // Next.js buffers proxied request bodies and silently truncates them at 10 MB by default,
    // which corrupts uploads. Keep this above the API's MAX_UPLOAD_MB (25 MB) plus multipart
    // overhead, so oversized files still reach the API whole and get a clear 413.
    proxyClientMaxBodySize: "32mb",
  },
  // The default bottom-left position covers the sidebar's "Sign out" button.
  devIndicators: { position: "bottom-right" },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiInternalUrl}/api/:path*` }];
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
