import { request } from "../../shared/http.js"

export function listNets() {
  return request("/api/nets")
}

export function searchNet(netId, query) {
  const target = netId || "power-grid"
  const params = new URLSearchParams()
  if (query.q) params.set("q", query.q)
  if (query.noticeType) params.set("noticeType", query.noticeType)
  if (query.area) params.set("area", query.area)
  if (query.source) params.set("source", query.source)
  params.set("page", String(query.page || 1))
  params.set("size", String(query.size || 10))
  const text = params.toString()
  return {
    path: `/api/nets/${encodeURIComponent(target)}/notices?${text}`,
    run: () => request(`/api/nets/${encodeURIComponent(target)}/notices?${text}`),
  }
}

export function searchGrid(query) {
  return searchNet("power-grid", query)
}

export function readNetNotice(netId, contentId, source) {
  const target = netId || "power-grid"
  const params = new URLSearchParams()
  if (source) params.set("source", source)
  const path = `/api/nets/${encodeURIComponent(target)}/notices/${encodeURIComponent(contentId)}?${params}`
  return { path, run: () => request(path) }
}

export function readGrid(contentId, source) {
  return readNetNotice("power-grid", contentId, source)
}
