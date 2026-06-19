import { createRouter } from "./router.js";
import { registerEventRoutes } from "./routes/events.js";
import { registerOrderRoutes } from "./routes/orders.js";
import { registerReturnRoutes } from "./routes/returns.js";

export const router = createRouter();

registerOrderRoutes(router);
registerReturnRoutes(router);
registerEventRoutes(router);

export function handleRequest(method, path, request = {}) {
  return router.dispatch(method, path, request);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const summary = router.routes.map((route) => ({
    method: route.method,
    path: route.path,
    handler: route.handler.name,
  }));

  console.log(JSON.stringify({ routes: summary }, null, 2));
}
