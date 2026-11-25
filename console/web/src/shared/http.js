export async function request(url, options) {
  const response = await fetch(url, options)
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = data.detail
    const message = typeof detail === "string"
      ? detail
      : (data.message || "请求没有完成")
    throw new Error(message)
  }
  return data
}
