import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    formats: ["image/avif", "image/webp"],
    deviceSizes: [640, 750, 828, 1080, 1200, 1920],
    imageSizes: [32, 48, 64, 96, 128, 256, 384],
    minimumCacheTTL: 120,
    remotePatterns: [
      {
        protocol: "https",
        hostname: "images.weserv.nl",
        pathname: "/**",
      },
    ],
  },
};

export default nextConfig;
