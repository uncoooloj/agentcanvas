import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter } from "react-router-dom"
import "@fontsource-variable/plus-jakarta-sans/index.css"
import "./index.css"
import App from "./App.tsx"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"

function routerBasename(baseUrl: string) {
  if (!baseUrl || baseUrl === "/" || baseUrl === "./") return undefined
  return baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter basename={routerBasename(import.meta.env.BASE_URL)}>
      <TooltipProvider delayDuration={300}>
        <App />
      </TooltipProvider>
      <Toaster position="bottom-right" richColors />
    </BrowserRouter>
  </StrictMode>
)
