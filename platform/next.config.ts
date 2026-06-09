import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 用 127.0.0.1 打开时，否则 dev HMR 被拦会导致页面白屏
  allowedDevOrigins: ["127.0.0.1", "localhost", "192.168.1.2"],
};

export default nextConfig;
