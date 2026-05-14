/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // Allow Next.js dev-server HMR/WebSocket connections from the VM's LAN IP.
  // Without this, hot-reload breaks when you open the app via the IP address.
  experimental: {
    allowedDevOrigins: [
      "http://172.31.8.102:3001",
      "http://172.31.8.102:3000",
    ],
  },
};

export default nextConfig;
