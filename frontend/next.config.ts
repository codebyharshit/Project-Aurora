import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  devIndicators: false, // keeps the "N" bubble out of demo recordings
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
