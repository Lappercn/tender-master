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
    <el-row :gutter="16" class="gap">
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card shadow="hover"><el-statistic title="正在采集" :value="running.length" /><p class="el-text">共 {{ sources.length }} 个源头</p></el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card shadow="hover"><el-statistic title="公告总量" :value="storage.noticeCount || 0" /><p class="el-text">今日新插入 {{ today.inserted || 0 }}</p></el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card shadow="hover"><el-statistic title="今日采集保存" :value="today.collected || 0" /><p class="el-text">库 {{ storage.current || "—" }}</p></el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card shadow="hover">
          <el-statistic title="内存占用" :value="memory.percent || 0" suffix="%" />
          <el-progress :percentage="memory.percent || 0" :show-text="false" />
          <p class="el-text">{{ gb(memory.used) }} / {{ gb(memory.total) }} · 浏览器 {{ nodes.browsers || 0 }}</p>
        </el-card>
      </el-col>
    </el-row>
    <el-card shadow="never">
      <template #header>采集源头</template>
      <el-table :data="paged" empty-text="还没有源头">
        <el-table-column prop="name" label="源头" min-width="220" />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.running ? 'success' : 'info'">{{ row.running ? "采集中" : "未运行" }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进程" width="120">
          <template #default="{ row }">{{ row.pid || "—" }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180">
          <template #default="{ row }">
            <el-button link type="primary" :disabled="row.running || busy" @click="start(row.id)">启动</el-button>
            <el-button link type="danger" :disabled="!row.running || busy" @click="askStop(row)">关闭</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="size"
          :total="sources.length"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          background
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue"
import { confirmStop, tell } from "../../shared/feedback.js"
import { listSources, startSource, stopSource } from "../collect/api.js"
import { nodeStatus } from "../nodes/api.js"
import { storageStatus } from "../storage/api.js"

const sources = ref([])
const storage = ref({})
const nodes = ref({})
const ready = ref(false)
const busy = ref(false)
const page = ref(1)
const size = ref(10)
const running = computed(() => sources.value.filter(item => item.running))
const paged = computed(() => sources.value.slice((page.value - 1) * size.value, page.value * size.value))
const today = computed(() => (storage.value.days || [])[0] || {})
const memory = computed(() => nodes.value.host?.memory || {})
let timer = 0

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
