import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
  // ponytail: hero photo still hosted by Stitch; move it to src/images when the real photo exists.
  images: { remotePatterns: [new URL("https://lh3.googleusercontent.com/aida/**")] },
};

export default nextConfig;
