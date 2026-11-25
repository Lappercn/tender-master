import { request } from "../../shared/http.js"

export function listSources() {
  return request("/admin/sources/")
}

export function startSource(id) {
  return request(`/admin/sources/${id}/start`, { method: "POST" })
}

export function stopSource(id) {
  return request(`/admin/sources/${id}/stop`, { method: "POST" })
}

export function saveBrowser(id, profile) {
  return request(`/admin/sources/${id}/browser`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
  })
}

export function readLog(id) {
  return request(`/admin/sources/${id}/logs`)
}

export function readProgress(id) {
  return request(`/admin/sources/${id}/progress`)
}

export function saveCollect(body) {
  return request("/admin/sources/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}
