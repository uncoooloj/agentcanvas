export function createRouter() {
  const routes = [];

  function add(method, path, handler) {
    routes.push({ method, path, handler });
    return api;
  }

  const api = {
    routes,
    get(path, handler) {
      return add("GET", path, handler);
    },
    post(path, handler) {
      return add("POST", path, handler);
    },
    dispatch(method, path, request = {}) {
      const route = routes.find(
        (candidate) => candidate.method === method && routeMatches(candidate.path, path)
      );

      if (!route) {
        return { status: 404, body: { error: "not_found", path } };
      }

      return route.handler({
        ...request,
        method,
        path,
        params: routeParams(route.path, path),
      });
    },
  };

  return api;
}

function routeMatches(pattern, path) {
  const patternParts = splitPath(pattern);
  const pathParts = splitPath(path);

  if (patternParts.length !== pathParts.length) {
    return false;
  }

  return patternParts.every(
    (part, index) => part.startsWith(":") || part === pathParts[index]
  );
}

function routeParams(pattern, path) {
  const params = {};
  const patternParts = splitPath(pattern);
  const pathParts = splitPath(path);

  patternParts.forEach((part, index) => {
    if (part.startsWith(":")) {
      params[part.slice(1)] = pathParts[index];
    }
  });

  return params;
}

function splitPath(path) {
  return path.split("/").filter(Boolean);
}
