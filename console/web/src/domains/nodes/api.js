import { request } from "../../shared/http.js"

export function nodeStatus() {
  return request("/admin/nodes/")
}
