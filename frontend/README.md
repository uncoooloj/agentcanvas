# AgentCanvas Frontend

This is the React/Vite source for the local AgentCanvas browser UI.

The built files are written to `../agentcanvas/web`, which is what the Python
server packages and serves.

## Commands

```bash
npm install
npm run build
npm run dev
```

The normal product path is still the Python CLI:

```bash
agentcanvas start --workspace /path/to/project
agentcanvas start --demo
agentcanvas start
```

Startup modes should stay obvious in the UI:

- `start` means no project is open yet.
- `start --demo` means the bundled sample project is open.
- `start --workspace` means AgentCanvas is reading and writing
  `.agentcanvas/` files beside the user's project.

The frontend should read the display canvas from `.agentcanvas/canvas.ir.json`
through the local API. The map is agent-authored from indexed evidence; parser
output is supporting detail, not the visible user-facing story.

Use `npm run dev` only when actively working on the UI.
