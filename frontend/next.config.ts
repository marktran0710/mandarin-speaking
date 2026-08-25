import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  agentRules: false,
  pageExtensions: ["page.tsx", "page.ts", "route.ts", "route.tsx"],
  typescript: {
    tsconfigPath: "tsconfig.next.json",
  },
  async redirects() {
    return [
      { source: "/teacher.html", destination: "/manage?role=teacher", permanent: false },
      { source: "/admin.html", destination: "/manage?role=admin", permanent: false },
      { source: "/instructor-demo.html", destination: "/", permanent: false },
    ];
  },
};

export default nextConfig;
