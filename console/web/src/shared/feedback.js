import { ElMessage, ElMessageBox } from "element-plus"

export function tell(message, type = "success") {
  ElMessage({ message, type, duration: 2500 })
}

export function confirmStop(name) {
  return ElMessageBox.confirm(
    `将关闭「${name}」，并清掉这次拉起的 Chrome。`,
    "关闭采集",
    {
      type: "warning",
      confirmButtonText: "关闭",
      cancelButtonText: "取消",
    },
  )
}

export function confirmRemove(title) {
  return ElMessageBox.confirm(
    `将删除「${title}」。删除后开放查询里也看不到这条。`,
    "删除公告",
    {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    },
  )
}
