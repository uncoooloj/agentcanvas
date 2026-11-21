# AgentCanvas Brand & Design Guide — "Warm Drafting Studio"

AgentCanvas is a local-first spatial studio for seeing what a codebase does, reviewing behavioral diffs visually, and steering coding agents directly.

Our aesthetic is **Warm Drafting Studio**: the calm, tactile precision of an architectural drafting table meets the speed and clarity of modern keyboard-first developer tools (Linear, Raycast, tldraw, Agentation).

---

## 1. Visual Principles

1. **Drafting Paper, Never Generic SaaS Slop.** Warm cream vellum in light mode, warm obsidian in dark mode. Zero neon purple-blue gradients, zero glossy 3D clichés, zero decorative clutter.
2. **Spatial Truth First.** Every node on the canvas carries its real file/line anchor (`src/orders/checkout.ts:42`) in crisp monospace — plain-English clarity without hiding engineering reality.
3. **Color Means Something.** Color is reserved strictly for semantic roles, diff states, live agent energy, and spatial pins. Chrome stays calm and monochrome.
4. **Immediate, Tactile Motion.** Transitions stay on the compositor (`opacity`, `transform`). Respect `prefers-reduced-motion` everywhere; pair hover-revealed controls with `:focus-within` and touch visibility.

---

## 2. Color System

### Surfaces & Ink

| Token | Light Mode (Warm Drafting Paper) | Dark Mode (Warm Obsidian Studio) | Usage |
| :--- | :--- | :--- | :--- |
| `--background` | `hsl(42 40% 96.5%)` / `#F8F5EE` | `hsl(30 8% 9%)` / `#181614` | Studio canvas & page ground |
| `--card` | `hsl(44 50% 99%)` / `#FFFDF9` | `hsl(30 7% 12%)` / `#201E1B` | Flow nodes, floating panels, drawers |
| `--foreground` | `hsl(30 10% 9%)` / `#191715` | `hsl(40 20% 94%)` / `#F2EFE9` | Primary headings & ink |
| `--muted-foreground` | `hsl(34 7% 42%)` / `#736C63` | `hsl(38 8% 62%)` / `#A69F95` | Captions, file paths, metadata |
| `--border` | `hsl(38 22% 87%)` / `#E5DEC9` | `hsl(33 7% 20%)` / `#36332E` | Hairlines, canvas dot-grid, edges |

### Signature Accents

| Name | Hex | Role |
| :--- | :--- | :--- |
| **Terracotta Clay** (`clay`) | `#D97757` | Brand accent, spatial pin markers, active agent focus, Build CTA |
| **Drafting Gold** (`gold`) | `#EDA100` | Trigger highlights, modified diff indicators, staleness cues |

### Node Role Palette

| Role | Meaning | Light Surface / Ink | Accent |
| :--- | :--- | :--- | :--- |
| **When** (`--when-*`) | Trigger, HTTP route, webhook, cron, user action | `hsl(38 80% 92%)` / `hsl(28 75% 28%)` | `hsl(32 88% 50%)` |
| **Do** (`--act-*`) | Core action, service call, write, notification | `hsl(162 48% 91%)` / `hsl(168 68% 22%)` | `hsl(165 65% 38%)` |
| **Decision** (`--rule-*`) | Branch, guard, business rule | `hsl(250 55% 94%)` / `hsl(250 48% 42%)` | `hsl(250 55% 62%)` |

### Visual Behavioral Diff States

| Diff State | Visual Treatment | Label |
| :--- | :--- | :--- |
| `added` | Crisp emerald border + soft emerald surface wash | `+ Added` |
| `modified` | Warm amber/gold border + soft amber wash | `~ Modified` |
| `removed` | Muted terracotta-red dashed border + strikethrough title | `- Removed` |
| `verified` | Emerald checkmark pill with verification check reference | `Verified` |
| `stale` | Subtle gold indicator dot when cited files changed since `git_head` | `Stale` |

---

## 3. Typography

- **Primary UI & Display:** **`Open Runde`** (self-hosted optimized `.woff2` subsets in `frontend/src/assets/fonts/`).
  - Editorial display: `font-bold tracking-[-0.03em] leading-[1.02]`
  - Studio titles: `font-semibold tracking-[-0.015em]`
  - Body & node copy: `13px–15px`, relaxed line height, tabular numerals for counters and diffs.
- **Code, Paths & Telemetry:** `ui-monospace, SFMono-Regular, Menlo, monospace` — used for file:line anchors, git branches, CLI commands, and live streaming agent logs.

---

## 4. Spatial Canvas Craft

- **Dot-grid drafting canvas:** Subtle radial/dot pattern (`gap: 20px`) that anchors spatial panning and zooming without visual noise.
- **Three zoom depths:**
  1. **System** — Services, apps, workers, databases, and external APIs with protocol-labeled edges.
  2. **Flows** — End-to-end product journeys laid out cleanly with ELK + dynamic-height cards (zero clipping).
  3. **Diff** — Behavioral diff overlay highlighting exactly what a branch, PR, or proposed agent plan adds, modifies, or removes.
- **Spatial Steering:** Users interact by selecting nodes (`@node`), dropping terracotta pins on any step, and steering via the floating `⌘K` Command Dock (`Plan Diff` → visual approval → `Build`).

---

## 5. Voice & Copy

- **Clear, grounded, developer-respectful.** Plain English for product behavior; exact paths, symbols, and commands when technical precision matters.
- **Truthful status only.** Never claim an agent is working unless a live run is streaming real events. Always distinguish `Interactive Sandbox` from live local workspaces.
- **Zero ceremony.** Initiation takes one command (`agentcanvas .` or `agentcanvas diff main..HEAD`) — never a multi-page setup manual.

---

## 6. Brand Assets

- Primary Open Graph / editorial hero artwork: `frontend/public/og-image.png` (isometric Warm Drafting Studio diagram on `#F8F5EE` dot-grid paper).
- Geometric brand mark: `frontend/src/components/BrandMark.tsx` & `frontend/public/logo-mark.svg`.
