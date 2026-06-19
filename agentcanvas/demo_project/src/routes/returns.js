import { requestReturnFlow } from "../actions/request-return.js";

export function registerReturnRoutes(router) {
  router.post("/returns", createReturnRoute);
}

export function createReturnRoute(request) {
  return requestReturnFlow(request.body || {});
}
