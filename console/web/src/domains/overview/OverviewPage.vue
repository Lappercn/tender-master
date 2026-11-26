<template>
  <div v-loading="!ready">
    <el-alert
      v-if="ready && !storage.online"
      class="gap"
      type="warning"
      show-icon
      :closable="false"
      title="数据库未连通"
      :description="storage.reason || '采集结果会先写在本机暂存。'"
    />
    <el-row :gutter="16" class="kpi-row">
      <el-col :xs="24" :sm="12" :md="6">
        <el-card shadow="hover" class="kpi-card">
          <el-statistic title="正在运行采集源" :value="running.length" />
          <p class="kpi-sub">
            <span class="status-dot" :class="running.length ? 'is-running' : 'is-idle'"></span>
            已注册共 <strong>{{ sources.length }}</strong> 个政企/央国企源头
          </p>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card shadow="hover" class="kpi-card kpi-green">
          <el-statistic title="库存标讯公告总量" :value="storage.noticeCount || 0" />
          <p class="kpi-sub">今日新去重入库 <strong>{{ today.inserted || 0 }}</strong> 条</p>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card shadow="hover" class="kpi-card kpi-amber">
          <el-statistic title="今日任务采集保存" :value="today.collected || 0" />
          <p class="kpi-sub">当前主存储库：<strong>{{ storage.current || "—" }}</strong></p>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card shadow="hover" class="kpi-card kpi-purple">
          <el-statistic title="主机内存负载" :value="memory.percent || 0" suffix="%" />
          <el-progress
            :percentage="memory.percent || 0"
            :show-text="false"
            :stroke-width="6"
            :color="memory.percent > 85 ? '#ef4444' : '#8b5cf6'"
            style="margin-top: 6px"
          />
          <p class="kpi-sub">{{ gb(memory.used) }} / {{ gb(memory.total) }} · 受控浏览器 <strong>{{ nodes.browsers || 0 }}</strong> 个</p>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never">
      <template #header>
        <div class="bar">
          <span>全量采集源头状态与一键启停（共 {{ sources.length }} 个）</span>
          <el-input
            v-model="keyword"
            clearable
            size="small"
            placeholder="搜索平台名称或所属网..."
            style="width: 240px"
          />
        </div>
      </template>
      <el-table :data="paged" empty-text="还没有源头" stripe>
        <el-table-column prop="name" label="采集平台名称" min-width="230" show-overflow-tooltip>
          <template #default="{ row }">
            <strong>{{ row.name }}</strong>
          </template>
        </el-table-column>
        <el-table-column label="所属六张网" width="140">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.netName || "新型电网" }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="覆盖栏目数" width="120">
          <template #default="{ row }">
            <span class="el-text">{{ (row.channels || []).length }} 个公开栏目</span>
          </template>
        </el-table-column>
        <el-table-column label="运行状态" width="130">
          <template #default="{ row }">
            <el-tag :type="row.running ? 'success' : 'info'" effect="light" size="small">
              <span class="status-dot" :class="row.running ? 'is-running' : 'is-idle'"></span>
              {{ row.running ? "采集中" : "待机未运行" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进程 PID" width="110">
          <template #default="{ row }">
            <code v-if="row.pid" style="color: #059669; font-weight: 600">{{ row.pid }}</code>
            <span v-else class="el-text" style="color: #cbd5e1">—</span>
          </template>
        </el-table-column>
        <el-table-column label="快捷操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="!row.running"
              size="small"
              type="primary"
              plain
              :disabled="busy"
              @click="start(row.id)"
            >启动采集</el-button>
            <el-button
              v-else
              size="small"
              type="danger"
              plain
              :disabled="busy"
              @click="askStop(row)"
            >停止进程</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="size"
          :total="filtered.length"
          :page-sizes="[10, 15, 20, 50]"
          layout="total, sizes, prev, pager, next"
          background
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue"
import { confirmStop, tell } from "../../shared/feedback.js"
import { listSources, startSource, stopSource } from "../collect/api.js"
import { nodeStatus } from "../nodes/api.js"
import { storageStatus } from "../storage/api.js"

const sources = ref([])
const storage = ref({})
const nodes = ref({})
const ready = ref(false)
const busy = ref(false)
const keyword = ref("")
const page = ref(1)
const size = ref(10)
const running = computed(() => sources.value.filter(item => item.running))
const filtered = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  if (!q) return sources.value
  return sources.value.filter(
    item =>
      (item.name || "").toLowerCase().includes(q) ||
      (item.id || "").toLowerCase().includes(q) ||
      (item.netName || "").toLowerCase().includes(q)
  )
})
const paged = computed(() => filtered.value.slice((page.value - 1) * size.value, page.value * size.value))
const today = computed(() => (storage.value.days || [])[0] || {})
const memory = computed(() => nodes.value.host?.memory || {})
let timer = 0

watch(keyword, () => {
  page.value = 1
})

function gb(bytes) {
  const value = Number(bytes) || 0
  if (!value) return "0 GB"
  return `${(value / 1024 ** 3).toFixed(1)} GB`
}
async function load() {
  const [sourceData, storageData, nodeData] = await Promise.all([listSources(), storageStatus(), nodeStatus()])
  sources.value = sourceData.items || []
  storage.value = storageData
  nodes.value = nodeData
  ready.value = true
}
async function start(id) {
  await run(() => startSource(id))
}
async function askStop(item) {
  try {
    await confirmStop(item.name)
  } catch {
    return
  }
  await run(() => stopSource(item.id))
}
async function run(action) {
  busy.value = true
  try {
    const data = await action()
    if (data.ok === false) throw new Error(data.message || "操作没有完成")
    tell(data.message || "已完成")
    await load()
  } catch (error) {
    tell(error.message, "error")
  } finally {
    busy.value = false
  }
}
function tick() {
  if (document.visibilityState !== "visible") return
  load().catch(error => tell(error.message, "error"))
}
onMounted(() => {
  tick()
  timer = setInterval(tick, 8000)
  document.addEventListener("visibilitychange", tick)
})
onUnmounted(() => {
  clearInterval(timer)
  document.removeEventListener("visibilitychange", tick)
})
</script>
