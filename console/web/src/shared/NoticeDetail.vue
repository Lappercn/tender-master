<template>
  <template v-if="detail">
    <section v-for="group in groups" :key="group.title">
      <h3>{{ group.title }}</h3>
      <el-descriptions :column="2" border>
        <el-descriptions-item v-for="field in group.fields" :key="field.key" :label="field.label" :span="field.span || 1">
          <a v-if="field.key === 'url' && detail.url" :href="detail.url" target="_blank" rel="noreferrer">{{ detail.url }}</a>
          <span v-else>{{ text(detail[field.key], field.key) }}</span>
        </el-descriptions-item>
      </el-descriptions>
    </section>

    <h3>联系人</h3>
    <el-table :data="contactRows" border empty-text="没有联系人">
      <el-table-column v-for="column in contactColumns" :key="column" :label="contactLabel(column)" min-width="140">
        <template #default="{ row }">{{ text(row[column]) }}</template>
      </el-table-column>
    </el-table>

    <h3>正文</h3>
    <p class="field-label">摘要</p>
    <pre class="body">{{ text(detail.briefText) }}</pre>
    <p class="field-label">正文</p>
    <div v-if="bodyBlocks.length">
      <template v-for="(block, index) in bodyBlocks" :key="index">
        <pre v-if="block.type === 'text'" class="body">{{ block.value }}</pre>
        <div v-else class="table-wrap">
          <table class="notice-table">
            <tbody>
              <tr v-for="(line, ri) in block.rows" :key="ri">
                <td v-for="(cell, ci) in line" :key="ci">{{ cell }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </div>
    <pre v-else class="body">—</pre>
    <el-descriptions class="gap" :column="2" border>
      <el-descriptions-item label="原始网页">{{ rawHtmlText }}</el-descriptions-item>
    </el-descriptions>

    <h3>附件</h3>
    <el-descriptions class="gap" :column="2" border>
      <el-descriptions-item label="有附件">{{ text(detail.hasAnnex) }}</el-descriptions-item>
      <el-descriptions-item label="页面上的附件名">{{ text(annexNames) }}</el-descriptions-item>
      <el-descriptions-item label="原文件地址" :span="2">
        <pre class="body">{{ text(detail.fileUrl) }}</pre>
      </el-descriptions-item>
    </el-descriptions>
    <el-table :data="fileRows" border empty-text="没有附件记录">
      <el-table-column label="文件" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">{{ text(row.name) }}</template>
      </el-table-column>
      <el-table-column label="大小" width="90">
        <template #default="{ row }">{{ sizeText(row.size) }}</template>
      </el-table-column>
      <el-table-column label="已下载" width="90">
        <template #default="{ row }">{{ text(row.ok) }}</template>
      </el-table-column>
      <el-table-column label="失败原因" min-width="140" show-overflow-tooltip>
        <template #default="{ row }">{{ text(row.error) }}</template>
      </el-table-column>
      <el-table-column label="本地路径" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">{{ text(row.path) }}</template>
      </el-table-column>
      <el-table-column label="原地址" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">{{ text(row.sourceUrl) }}</template>
      </el-table-column>
      <el-table-column label="下载" width="90">
        <template #default="{ row }">
          <a v-if="row.ok && row.download" :href="row.download">下载</a>
          <span v-else>—</span>
        </template>
      </el-table-column>
    </el-table>

    <h3>采集附带</h3>
    <el-descriptions :column="2" border>
      <el-descriptions-item v-for="field in extraFields" :key="field.key" :label="field.label" :span="field.span || 1">
        {{ text(field.value) }}
      </el-descriptions-item>
    </el-descriptions>

    <h3 v-if="restFields.length">其他字段</h3>
    <el-descriptions v-if="restFields.length" :column="2" border>
      <el-descriptions-item v-for="field in restFields" :key="field.key" :label="field.label" :span="2">
        {{ text(field.value) }}
      </el-descriptions-item>
    </el-descriptions>
  </template>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({
  detail: { type: Object, default: null },
})

const GROUPS = [
  {
    title: "公告",
    fields: [
      { key: "title", label: "标题", span: 2 },
      { key: "source", label: "来源" },
      { key: "bizNet", label: "所属" },
      { key: "noticeType", label: "公告类型" },
      { key: "category", label: "栏目" },
      { key: "channel", label: "栏目编号" },
      { key: "area", label: "地区" },
      { key: "industry", label: "行业" },
      { key: "createTime", label: "发布时间" },
      { key: "projectStatus", label: "项目状态" },
      { key: "projectCode", label: "项目编号", span: 2 },
      { key: "siteNoticeId", label: "站点编号", span: 2 },
      { key: "url", label: "原文", span: 2 },
    ],
  },
  {
    title: "采购与代理",
    fields: [
      { key: "purchaser", label: "采购人" },
      { key: "agent", label: "代理机构" },
      { key: "purchaseMethod", label: "采购方式" },
      { key: "budget_label", label: "预算项" },
      { key: "budget", label: "预算原文", span: 2 },
      { key: "tenderEndTime", label: "截止时间", span: 2 },
    ],
  },
  {
    title: "成交",
    fields: [
      { key: "winningBidder", label: "中标人" },
      { key: "winningAmount", label: "中标金额" },
    ],
  },
  {
    title: "这条记录",
    fields: [
      { key: "contentId", label: "公告指纹", span: 2 },
      { key: "crawlerId", label: "采集源头" },
      { key: "script", label: "采集脚本" },
      { key: "nodeId", label: "节点" },
      { key: "schemaVersion", label: "字段版本" },
      { key: "crawl_time", label: "采集时间" },
      { key: "storedAt", label: "入库时间" },
      { key: "storedBy", label: "入库节点" },
      { key: "processStatus", label: "整理状态" },
      { key: "processNote", label: "整理说明", span: 2 },
      { key: "keywords", label: "关键词" },
      { key: "highlightedWords", label: "高亮词" },
      { key: "tags", label: "标签" },
      { key: "onclick", label: "原页面点击" },
    ],
  },
]

const CONTACT_LABELS = { name: "姓名", phone: "电话", role: "角色", email: "邮箱" }
const EXTRA_LABELS = { listTitle: "列表标题", annexNames: "页面附件名", detailTruncated: "正文被截断" }
const STATUS = { pending: "待整理", degraded: "存储降级，原文仍在" }
const OWN = new Set([
  "contacts", "files", "fileUrl", "extra", "detail", "detailText", "briefText", "hasRawHtml", "_id",
])

const groups = GROUPS
const detail = computed(() => props.detail)

const contactRows = computed(() => {
  const rows = Array.isArray(detail.value?.contacts) ? detail.value.contacts.filter(item => item && typeof item === "object") : []
  return rows.length ? rows : [{ name: "", phone: "" }]
})
const contactColumns = computed(() => {
  const keys = ["name", "phone"]
  for (const row of contactRows.value) {
    for (const key of Object.keys(row)) {
      if (!keys.includes(key)) keys.push(key)
    }
  }
  return keys
})
const fileRows = computed(() => (Array.isArray(detail.value?.files) ? detail.value.files : []))
const annexNames = computed(() => detail.value?.extra?.annexNames)
const extraFields = computed(() => {
  const extra = detail.value?.extra && typeof detail.value.extra === "object" ? detail.value.extra : {}
  const keys = [...new Set([...Object.keys(EXTRA_LABELS), ...Object.keys(extra)])].filter(key => key !== "annexNames")
  return keys.map(key => ({
    key,
    label: EXTRA_LABELS[key] || key,
    value: extra[key],
    span: key === "listTitle" ? 2 : 1,
  }))
})
const restFields = computed(() => {
  const used = new Set(OWN)
  for (const group of GROUPS) {
    for (const field of group.fields) used.add(field.key)
  }
  return Object.keys(detail.value || {})
    .filter(key => !used.has(key))
    .sort()
    .map(key => ({ key, label: key, value: detail.value[key] }))
})
const bodyBlocks = computed(() => readBody(detail.value?.detailText))
const rawHtmlText = computed(() => {
  if (detail.value?.hasRawHtml === true) return "已保存"
  if (detail.value?.hasRawHtml === false) return "没有"
  return "—"
})

function contactLabel(key) {
  return CONTACT_LABELS[key] || key
}

function text(value, key) {
  if (key === "processStatus" && STATUS[value]) return STATUS[value]
  if (value === 0) return "0"
  if (value === false) return "否"
  if (value === true) return "是"
  if (value === null || value === undefined || value === "") return "—"
  if (Array.isArray(value)) {
    if (!value.length) return "—"
    if (value.every(item => item === null || ["string", "number", "boolean"].includes(typeof item))) {
      return value.map(item => (item === null || item === undefined || item === "" ? "—" : String(item))).join("\n")
    }
    return JSON.stringify(value, null, 2)
  }
  if (typeof value === "object") return JSON.stringify(value, null, 2)
  return String(value)
}

function sizeText(size) {
  const value = Number(size) || 0
  if (value <= 0) return "—"
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

function readBody(source) {
  const blocks = []
  let paragraph = []
  let table = []
  function flushParagraph() {
    const value = paragraph.join("\n").trim()
    paragraph = []
    if (value) blocks.push({ type: "text", value })
  }
  function flushTable() {
    const rows = []
    for (const line of table) {
      const cells = splitRow(line)
      if (!cells.length || cells.every(cell => /^:?-{3,}:?$/.test(cell))) continue
      rows.push(cells)
    }
    table = []
    if (rows.length) blocks.push({ type: "table", rows })
  }
  for (const line of String(source || "").split("\n")) {
    if (/^\s*\|.*\|\s*$/.test(line)) {
      flushParagraph()
      table.push(line)
    } else {
      if (table.length) flushTable()
      paragraph.push(line)
    }
  }
  if (table.length) flushTable()
  flushParagraph()
  return blocks
}

function splitRow(line) {
  const body = line.trim().replace(/^\|/, "").replace(/\|$/, "")
  const cells = []
  let current = ""
  for (let i = 0; i < body.length; i += 1) {
    if (body[i] === "\\" && body[i + 1] === "|") {
      current += "|"
      i += 1
    } else if (body[i] === "|") {
      cells.push(current.trim())
      current = ""
    } else {
      current += body[i]
    }
  }
  cells.push(current.trim())
  return cells
}
</script>

<style scoped>
h3 { margin: 18px 0 8px; font-size: 15px; font-weight: 600; }
h3:first-child { margin-top: 0; }
.field-label { margin: 12px 0 4px; font-size: 13px; color: var(--el-text-color-secondary, #909399); }
.gap { margin-bottom: 12px; }
.table-wrap { overflow-x: auto; margin-top: 8px; }
.notice-table { width: 100%; border-collapse: collapse; font-size: 13px; line-height: 1.6; }
.notice-table td { border: 1px solid var(--el-border-color, #dcdfe6); padding: 8px 10px; vertical-align: top; }
</style>
