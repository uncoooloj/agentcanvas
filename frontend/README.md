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

Use `npm run dev` only when actively working on the UI.
