import { request } from "../../shared/http.js"

export function nodeStatus() {
  return request("/admin/nodes/")
}

export function saveNodeConfig(body) {
  return request("/admin/nodes/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}

export function deleteNodeConfig(nodeId) {
  return request(`/admin/nodes/config/${encodeURIComponent(nodeId)}`, {
    method: "DELETE",
  })
}

export function dispatchClusterTasks(body = {}) {
  return request("/admin/nodes/dispatch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}

export function recoverClusterTasks() {
  return request("/admin/nodes/recover", { method: "POST" })
}

export function clearClusterTasks(status = "") {
  const qs = status ? `?status=${encodeURIComponent(status)}` : ""
  return request(`/admin/nodes/tasks/clear${qs}`, { method: "POST" })
}

export function workOnce(nodeId = "") {
  const qs = nodeId ? `?nodeId=${encodeURIComponent(nodeId)}` : ""
  return request(`/admin/nodes/work-once${qs}`, { method: "POST" })
}

export function resetNodeBreaker(nodeId, crawlerId = "") {
  return request("/admin/nodes/breaker/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nodeId, crawlerId }),
  })
}

export function updateClusterSchedule(body) {
  return request("/admin/nodes/schedules", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}

export function startClusterDaemon(role, nodeId = "") {
  return request("/admin/nodes/daemons/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role, nodeId }),
  })
}

export function stopClusterDaemon(role, nodeId = "") {
  return request("/admin/nodes/daemons/stop", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role, nodeId }),
  })
}
