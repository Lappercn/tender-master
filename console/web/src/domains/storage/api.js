import { request } from "../../shared/http.js"

export function storageStatus() {
  return request("/admin/storage/")
}

export function pageRuns(params) {
  const search = new URLSearchParams()
  if (params.crawler) search.set("crawler", params.crawler)
  search.set("page", String(params.page || 1))
  search.set("size", String(params.size || 10))
  return request(`/admin/storage/runs?${search}`)
}
