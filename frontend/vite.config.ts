import path from "path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

// Build output goes straight into the dir the Python CLI serves (agentcanvas/web).
// Keep the default base at "/" for the local Python CLI. Cloudflare/subpath
// builds can opt in with AGENTCANVAS_VITE_BASE=/agentcanvas/.
function viteBasePath() {
  const configured = process.env.AGENTCANVAS_VITE_BASE?.trim()
  if (!configured) return "/"
  if (configured === "./") return configured
  const withLeadingSlash = configured.startsWith("/") ? configured : `/${configured}`
  return withLeadingSlash.endsWith("/") ? withLeadingSlash : `${withLeadingSlash}/`
}

function buildOutDir() {
  return process.env.AGENTCANVAS_VITE_OUT_DIR?.trim() || "../agentcanvas/web"
}

export default defineConfig({
  base: viteBasePath(),
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  build: {
    outDir: buildOutDir(),
    emptyOutDir: true,
  },
  server: { port: 5273 },
})
