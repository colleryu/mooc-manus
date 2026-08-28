import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "**.myqcloud.com",
      },
    ],
  },
  // Next 16.3 默认的 CLI 类型检查器在当前运行环境无法捕获 tsc 的
  // --showConfig 输出；项目使用 TypeScript 5，可安全使用编译器 API。
  experimental: {
    useTypeScriptCli: false,
  },
};

export default nextConfig;
