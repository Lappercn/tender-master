import { request } from "../../shared/http.js"

export function listNets() {
  return request("/api/nets")
}

export function searchGrid(query) {
  const params = new URLSearchParams()
  if (query.q) params.set("q", query.q)
  if (query.noticeType) params.set("noticeType", query.noticeType)
  if (query.area) params.set("area", query.area)
  if (query.source) params.set("source", query.source)
  params.set("page", String(query.page || 1))
  params.set("size", String(query.size || 10))
  const text = params.toString()
  return {
    path: `/api/nets/power-grid/notices?${text}`,
    run: () => request(`/api/nets/power-grid/notices?${text}`),
  }
}

export function readGrid(contentId, source) {
  const params = new URLSearchParams()
  if (source) params.set("source", source)
  const path = `/api/nets/power-grid/notices/${encodeURIComponent(contentId)}?${params}`
  return { path, run: () => request(path) }
}
