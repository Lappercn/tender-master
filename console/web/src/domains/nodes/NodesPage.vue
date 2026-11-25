<template>
  <div v-loading="!data">
    <el-row v-if="data" :gutter="16" class="gap">
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card shadow="hover">
          <el-statistic :title="`${host.system || ''} ${host.release || ''}`" :value="host.cpuCount || 0" suffix="核" />
          <p class="el-text">{{ host.hostname }} · Python {{ host.python }}</p>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card shadow="hover">
          <el-statistic title="内存占用" :value="memory.percent || 0" suffix="%" />
          <el-progress :percentage="memory.percent || 0" :show-text="false" />
          <p class="el-text">{{ gb(memory.used) }} / {{ gb(memory.total) }}</p>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card shadow="hover"><el-statistic title="采集进程" :value="data.crawlerCount || 0" /></el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card shadow="hover"><el-statistic title="浏览器进程" :value="data.browsers || 0" /></el-card>
      </el-col>
    </el-row>
    <el-card v-if="data" shadow="never" class="gap">
      <template #header>这台机器</template>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="处理器">{{ host.processor || "—" }}</el-descriptions-item>
        <el-descriptions-item label="正在采集">{{ runningText }}</el-descriptions-item>
      </el-descriptions>
    </el-card>
    <el-card v-if="data" shadow="never">
      <template #header>节点</template>
      <el-table :data="data.nodes" empty-text="还没有节点">
        <el-table-column prop="id" label="节点" width="160" />
        <el-table-column label="职责" min-width="180">
          <template #default="{ row }">{{ (row.roles || []).join("、") }}</template>
        </el-table-column>
        <el-table-column prop="accept" label="接收的源头" min-width="180" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue"
import { tell } from "../../shared/feedback.js"
import { nodeStatus } from "./api.js"

const data = ref(null)
const host = computed(() => data.value?.host || {})
const memory = computed(() => host.value.memory || {})
const runningText = computed(() => {
  const rows = data.value?.crawlers || []
  if (!rows.length) return "没有"
  return rows.map(item => `${item.name}（${item.pid}）`).join("、")
})
let timer = 0

function gb(bytes) {
  const value = Number(bytes) || 0
  if (!value) return "0 GB"
  return `${(value / 1024 ** 3).toFixed(1)} GB`
}
function tick() {
  if (document.visibilityState !== "visible") return
  nodeStatus().then(body => { data.value = body }).catch(error => tell(error.message, "error"))
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
