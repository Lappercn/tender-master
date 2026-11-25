<template>
  <div v-loading="!data">
    <el-alert
      v-if="data && !data.online"
      class="gap"
      type="warning"
      show-icon
      :closable="false"
      title="数据库未连通"
      :description="data.reason || '采集结果会先写在本机暂存。'"
    />
    <el-row v-if="data" :gutter="16" class="gap">
      <el-col :xs="24" :sm="12" :lg="6"><el-card shadow="hover"><el-statistic title="公告总量" :value="data.noticeCount || 0" /></el-card></el-col>
      <el-col :xs="24" :sm="12" :lg="6"><el-card shadow="hover"><el-statistic title="公告表" :value="(data.collections || []).length" /></el-card></el-col>
      <el-col :xs="24" :sm="12" :lg="6"><el-card shadow="hover"><el-statistic title="本机暂存" :value="data.spoolCount || 0" /></el-card></el-col>
      <el-col :xs="24" :sm="12" :lg="6"><el-card shadow="hover"><el-statistic :title="`当前库 ${data.current || ''}`" :value="size(data.dataBytes)" /></el-card></el-col>
    </el-row>
    <el-card v-if="data" shadow="never" class="gap">
      <template #header>库</template>
      <el-table :data="data.databases">
        <el-table-column prop="role" label="用途" width="120" />
        <el-table-column prop="name" label="库名" min-width="160" />
        <el-table-column label="公告" width="140">
          <template #default="{ row }">{{ row.holdsNotices ? "当前存放" : "不存放" }}</template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.exists ? 'success' : 'info'">{{ row.exists ? "已建库" : data.online ? "尚未写入" : "未连接" }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    <el-row v-if="data" :gutter="16">
      <el-col :xs="24" :lg="10">
        <el-card shadow="never">
          <template #header>公告表</template>
          <el-table :data="data.collections" empty-text="还没有公告表">
            <el-table-column prop="name" label="表" min-width="180" />
            <el-table-column prop="count" label="条数" width="100" />
          </el-table>
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="14">
        <el-card shadow="never">
          <template #header>最近 14 天</template>
          <el-table :data="dayPage" max-height="420" empty-text="还没有按天汇总">
            <el-table-column prop="day" label="日期" width="140" />
            <el-table-column prop="inserted" label="新插入" />
            <el-table-column prop="collected" label="采集保存" />
          </el-table>
          <div class="pager">
            <el-pagination
              v-model:current-page="dayPageNo"
              v-model:page-size="daySize"
              :total="(data.days || []).length"
              :page-sizes="[7, 14]"
              layout="total, sizes, prev, pager, next"
              background
            />
          </div>
          <p class="el-text">新插入是当天第一次写进公告库的条数。采集保存是当天任务记下的保存条数。</p>
        </el-card>
      </el-col>
    </el-row>
    <el-card shadow="never" style="margin-top: 16px">
      <template #header>
        <div class="bar">
          <span>采集记录</span>
          <el-input v-model="runCrawler" clearable placeholder="源头编号，如 sgcc_ecp" style="width: 240px" @change="loadRuns(1)" @clear="loadRuns(1)" />
        </div>
      </template>
      <el-table v-loading="runsLoading" :data="runs" empty-text="还没有采集记录">
        <el-table-column prop="startedAt" label="开始" min-width="170" />
        <el-table-column prop="crawlerName" label="源头" min-width="180" show-overflow-tooltip />
        <el-table-column prop="channel" label="栏目" min-width="100" />
        <el-table-column prop="spanLabel" label="范围" width="120" />
        <el-table-column prop="status" label="结果" width="110" />
        <el-table-column prop="saved" label="保存" width="80" />
        <el-table-column prop="error" label="说明" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.error || row.note || "—" }}</template>
        </el-table-column>
      </el-table>
      <div class="pager">
        <el-pagination
          v-model:current-page="runPage"
          v-model:page-size="runSize"
          :total="runTotal"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          background
          @current-change="loadRuns"
          @size-change="loadRuns(1)"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue"
import { tell } from "../../shared/feedback.js"
import { pageRuns, storageStatus } from "./api.js"

const data = ref(null)
const dayPageNo = ref(1)
const daySize = ref(7)
const runs = ref([])
const runTotal = ref(0)
const runPage = ref(1)
const runSize = ref(10)
const runCrawler = ref("")
const runsLoading = ref(false)
const dayPage = computed(() => {
  const days = data.value?.days || []
  const start = (dayPageNo.value - 1) * daySize.value
  return days.slice(start, start + daySize.value)
})
let timer = 0

function size(bytes) {
  const value = Number(bytes) || 0
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GB`
  if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toFixed(1)} MB`
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${value} B`
}
function tick() {
  if (document.visibilityState !== "visible") return
  storageStatus().then(body => { data.value = body }).catch(error => tell(error.message, "error"))
}
async function loadRuns(nextPage) {
  if (typeof nextPage === "number") runPage.value = nextPage
  runsLoading.value = true
  try {
    const body = await pageRuns({ crawler: runCrawler.value, page: runPage.value, size: runSize.value })
    runs.value = body.items || []
    runTotal.value = body.total || 0
  } catch (error) {
    runs.value = []
    runTotal.value = 0
    tell(error.message, "error")
  } finally {
    runsLoading.value = false
  }
}
onMounted(() => {
  tick()
  loadRuns()
  timer = setInterval(tick, 8000)
  document.addEventListener("visibilitychange", tick)
})
onUnmounted(() => {
  clearInterval(timer)
  document.removeEventListener("visibilitychange", tick)
})
</script>
