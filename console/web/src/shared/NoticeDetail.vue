<template>
  <template v-if="detail">
    <div class="detail-hero">
      <div class="detail-badges">
        <el-tag v-if="detail.bizNet" size="small" type="primary" effect="dark">{{ detail.bizNet }}</el-tag>
        <el-tag v-if="detail.noticeType" size="small" type="success" effect="light">{{ detail.noticeType }}</el-tag>
        <el-tag v-if="detail.area" size="small" type="info" effect="plain">{{ detail.area }}</el-tag>
        <span class="detail-date">{{ detail.createTime || "—" }}</span>
      </div>
      <h2 class="detail-title">{{ detail.title }}</h2>
      <div class="detail-fingerprint">
        <span>标题 MD5 指纹 (<code>contentId</code>)：</span>
        <code>{{ detail.contentId || "—" }}</code>
      </div>
    </div>

    <section v-for="group in groups" :key="group.title">
      <h3>{{ group.title }}</h3>
      <el-descriptions :column="2" border>
        <el-descriptions-item
          v-for="field in group.fields"
          :key="field.key"
          :label="field.label"
          :span="field.span || 1"
          width="105px"
        >
          <a v-if="field.key === 'url' && detail.url" :href="detail.url" target="_blank" rel="noreferrer" class="ext-link">
            {{ detail.url }} ↗
          </a>
          <strong v-else-if="field.key === 'budget' && detail.budget" style="color: #d97706">
            {{ text(detail[field.key], field.key) }}
          </strong>
          <span v-else>{{ text(detail[field.key], field.key) }}</span>
        </el-descriptions-item>
      </el-descriptions>
    </section>

    <h3>防错配提取联系人（50 字符邻近窗口配对）</h3>
    <el-table :data="contactRows" border empty-text="未从正文中提取到联系人">
      <el-table-column v-for="column in contactColumns" :key="column" :label="contactLabel(column)" min-width="140">
        <template #default="{ row }">
          <strong v-if="column === 'phone' && row[column]" style="color: #2563eb">{{ text(row[column]) }}</strong>
          <span v-else>{{ text(row[column]) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <h3>清洗后公告正文</h3>
    <template v-if="detail.briefText">
      <p class="field-label">核心摘要</p>
      <pre class="body">{{ text(detail.briefText) }}</pre>
    </template>
    <p class="field-label">正文内容</p>
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
    <el-descriptions class="gap" style="margin-top: 10px" :column="2" border>
      <el-descriptions-item label="原始网页存档" width="105px">
        <el-tag size="small" :type="detail.hasRawHtml ? 'success' : 'info'">{{ rawHtmlText }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="整理管道状态" width="105px">
        <el-tag size="small" type="warning" effect="plain">{{ text(detail.processStatus, 'processStatus') }}</el-tag>
      </el-descriptions-item>
    </el-descriptions>

    <h3>本地落盘标书与附件包</h3>
    <el-descriptions class="gap" :column="2" border>
      <el-descriptions-item label="含附件" width="105px">{{ text(detail.hasAnnex) }}</el-descriptions-item>
      <el-descriptions-item label="页面附件名" width="105px">{{ text(annexNames) }}</el-descriptions-item>
      <el-descriptions-item v-if="detail.fileUrl" label="原文件地址" :span="2">
        <pre class="body" style="max-height: 120px">{{ text(detail.fileUrl) }}</pre>
      </el-descriptions-item>
    </el-descriptions>
    <el-table :data="fileRows" border empty-text="没有本地附件记录">
      <el-table-column label="文件名" min-width="170" show-overflow-tooltip>
        <template #default="{ row }">{{ text(row.name) }}</template>
      </el-table-column>
      <el-table-column label="大小" width="90">
        <template #default="{ row }">{{ sizeText(row.size) }}</template>
      </el-table-column>
      <el-table-column label="落盘状态" width="95">
        <template #default="{ row }">
          <el-tag size="small" :type="row.ok ? 'success' : 'danger'">{{ row.ok ? "已落盘" : "未下载" }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="失败原因" min-width="130" show-overflow-tooltip>
        <template #default="{ row }">{{ text(row.error) }}</template>
      </el-table-column>
      <el-table-column label="本地路径" min-width="170" show-overflow-tooltip>
        <template #default="{ row }">{{ text(row.path) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="90" fixed="right">
        <template #default="{ row }">
          <el-button v-if="row.ok && row.download" link type="primary" tag="a" :href="row.download">下载</el-button>
          <span v-else>—</span>
        </template>
      </el-table-column>
    </el-table>

    <h3>采集元数据与入库追踪</h3>
    <el-descriptions :column="2" border>
      <el-descriptions-item v-for="field in extraFields" :key="field.key" :label="field.label" :span="field.span || 1" width="105px">
        {{ text(field.value) }}
      </el-descriptions-item>
    </el-descriptions>

    <h3 v-if="restFields.length">其他扩展字段</h3>
    <el-descriptions v-if="restFields.length" :column="2" border>
      <el-descriptions-item v-for="field in restFields" :key="field.key" :label="field.label" :span="2" width="105px">
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
    title: "基础信息",
    fields: [
      { key: "source", label: "来源平台" },
      { key: "bizNet", label: "所属六张网" },
      { key: "noticeType", label: "公告类型" },
      { key: "category", label: "采集栏目" },
      { key: "channel", label: "栏目代号" },
      { key: "area", label: "所属地区" },
      { key: "industry", label: "所属行业" },
      { key: "createTime", label: "发布时间" },
      { key: "projectStatus", label: "项目状态" },
      { key: "projectCode", label: "项目编号" },
      { key: "siteNoticeId", label: "站点编号", span: 2 },
      { key: "url", label: "原文链接", span: 2 },
    ],
  },
  {
    title: "商务核心（6 级漏斗提取）",
    fields: [
      { key: "purchaser", label: "采购人" },
      { key: "agent", label: "代理机构" },
      { key: "purchaseMethod", label: "采购方式" },
      { key: "budget_label", label: "命中级别" },
      { key: "budget", label: "预算/控制价", span: 2 },
      { key: "tenderEndTime", label: "截止时间", span: 2 },
    ],
  },
  {
    title: "中标与成交",
    fields: [
      { key: "winningBidder", label: "中标候选人" },
      { key: "winningAmount", label: "中标金额" },
    ],
  },
  {
    title: "系统溯源",
    fields: [
      { key: "crawlerId", label: "采集源头" },
      { key: "script", label: "执行脚本" },
      { key: "nodeId", label: "采集节点" },
      { key: "schemaVersion", label: "字段版本" },
      { key: "crawl_time", label: "采集时间" },
      { key: "storedAt", label: "入库时间" },
      { key: "storedBy", label: "入库节点" },
      { key: "processStatus", label: "整理状态" },
      { key: "processNote", label: "整理说明", span: 2 },
    ],
  },
]

const CONTACT_LABELS = { name: "联系人姓名", phone: "联系电话", role: "所属角色", email: "电子邮箱" }
const EXTRA_LABELS = { listTitle: "列表原题", annexNames: "页面附件名", detailTruncated: "正文截断" }
const STATUS = { pending: "待样本整理", degraded: "存储降级，原文仍在" }
const OWN = new Set([
  "title", "contentId", "contacts", "files", "fileUrl", "extra", "detail", "detailText", "briefText", "hasRawHtml", "_id",
  "keywords", "highlightedWords", "tags", "onclick",
])

const groups = GROUPS
const detail = computed(() => props.detail)

const contactRows = computed(() => {
  const rows = Array.isArray(detail.value?.contacts) ? detail.value.contacts.filter(item => item && typeof item === "object") : []
  return rows.length ? rows : []
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
  if (detail.value?.hasRawHtml === true) return "已保存 HTML 原文"
  if (detail.value?.hasRawHtml === false) return "未保存"
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
      return value.map(item => (item === null || item === undefined || item === "" ? "—" : String(item))).join("、")
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
.detail-hero {
  padding: 16px 18px;
  background: linear-gradient(135deg, #f8fafc 0%, #eff6ff 100%);
  border: 1px solid #dbeafe;
  border-radius: 10px;
  margin-bottom: 18px;
}
.detail-badges {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.detail-date {
  margin-left: auto;
  font-size: 12px;
  color: #64748b;
}
.detail-title {
  margin: 10px 0 8px;
  font-size: 17px;
  font-weight: 700;
  color: #0f172a;
  line-height: 1.5;
}
.detail-fingerprint {
  font-size: 12px;
  color: #64748b;
}
.detail-fingerprint code {
  color: #2563eb;
  font-weight: 600;
}
h3 {
  margin: 20px 0 10px;
  font-size: 14px;
  font-weight: 700;
  color: #1e293b;
  padding-left: 10px;
  border-left: 3px solid #2563eb;
}
.field-label {
  margin: 12px 0 4px;
  font-size: 13px;
  font-weight: 500;
  color: #64748b;
}
.gap { margin-bottom: 12px; }
.ext-link { color: #2563eb; text-decoration: none; word-break: break-all; }
.ext-link:hover { text-decoration: underline; }
.table-wrap { overflow-x: auto; margin-top: 8px; border-radius: 8px; border: 1px solid #e2e8f0; }
.notice-table { width: 100%; border-collapse: collapse; font-size: 13px; line-height: 1.6; }
.notice-table td { border: 1px solid #e2e8f0; padding: 8px 12px; vertical-align: top; min-width: 90px; }
.notice-table tr:first-child td { background: #f8fafc; font-weight: 600; }
</style>
