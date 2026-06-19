const BASE_PATH = "/agentcanvas"

export default {
  async fetch(request, env) {
    const url = new URL(request.url)

    if (url.pathname === BASE_PATH) {
      url.pathname = `${BASE_PATH}/`
      return Response.redirect(url.toString(), 308)
    }

    if (!url.pathname.startsWith(`${BASE_PATH}/`)) {
      return new Response("Not found", { status: 404 })
    }

    const assetUrl = new URL(request.url)
    assetUrl.pathname = assetUrl.pathname.slice(BASE_PATH.length) || "/"

    return env.ASSETS.fetch(new Request(assetUrl, request))
  },
}
