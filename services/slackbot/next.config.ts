import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.join(import.meta.dirname, "../.."),
  serverExternalPackages: ["@slack/bolt", "@slack/web-api", "@lmnr-ai/lmnr"],
};

export default nextConfig;
