import path from "path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

// Build output goes straight into the dir the Python CLI serves (agentcanvas/web).
// base:'/' so hashed assets load from /assets regardless of the client-side route
// (the server SPA-falls back to index.html for unknown paths).
export default defineConfig({
  base: "/",
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  build: {
    outDir: "../agentcanvas/web",
    emptyOutDir: true,
  },
  server: { port: 5273 },
})
