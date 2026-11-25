import { request } from "../../shared/http.js"

function query(params) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value))
  })
  const text = search.toString()
  return text ? `?${text}` : ""
}

export function listNotices(params) {
  return request(`/admin/notices/${query(params)}`)
}

export function readNotice(sourceId, contentId) {
  return request(`/admin/notices/${encodeURIComponent(sourceId)}/${encodeURIComponent(contentId)}`)
}

export function createNotice(body) {
  return request("/admin/notices/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}

export function updateNotice(sourceId, contentId, body) {
  return request(`/admin/notices/${encodeURIComponent(sourceId)}/${encodeURIComponent(contentId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}

export function deleteNotice(sourceId, contentId) {
  return request(`/admin/notices/${encodeURIComponent(sourceId)}/${encodeURIComponent(contentId)}`, {
    method: "DELETE",
  })
}

export function listCatalog() {
  return request("/api/nets")
}
