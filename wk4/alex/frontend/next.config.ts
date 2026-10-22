import type { NextConfig } from "next";

const cloudRunBuild = process.env.NEXT_OUTPUT_MODE === "standalone";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  ...(cloudRunBuild ? { output: "standalone" as const } : { output: "export" as const }),
  ...(cloudRunBuild
    ? {
        async headers() {
          return [
            {
              source: "/:path*",
              headers: [
                { key: "Strict-Transport-Security", value: "max-age=31536000" },
                { key: "X-Content-Type-Options", value: "nosniff" },
                { key: "X-Frame-Options", value: "DENY" },
                { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
                { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
              ],
            },
          ];
        },
      }
    : {}),
  images: {
    unoptimized: true
  },
  // Disable automatic trailing slash redirect for API routes
  trailingSlash: false,
};

export default nextConfig;
