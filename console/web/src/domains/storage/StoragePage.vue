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
    <el-row v-if="data" :gutter="16" class="kpi-row">
      <el-col :xs="24" :sm="12" :md="6">
        <el-card shadow="hover" class="kpi-card">
          <el-statistic title="公告总量" :value="data.noticeCount || 0" />
          <p class="kpi-sub">跨平台 MD5 指纹去重后入库总量</p>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card shadow="hover" class="kpi-card kpi-green">
          <el-statistic title="物理公告表" :value="(data.collections || []).length" />
          <p class="kpi-sub">按「六张网」领域或源头自动分表</p>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card shadow="hover" class="kpi-card kpi-amber">
          <el-statistic title="本机断网暂存 (Spool)" :value="data.spoolCount || 0" />
          <p class="kpi-sub">断网时落盘本地，恢复后无损回放</p>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card shadow="hover" class="kpi-card kpi-purple">
          <el-statistic :title="`当前主库 (${data.current || 'six_collect'})`" :value="size(data.dataBytes)" />
          <p class="kpi-sub">MongoDB 存储状态：{{ data.online ? "在线正常" : "离线暂存中" }}</p>
        </el-card>
      </el-col>
    </el-row>

    <el-card v-if="data" shadow="never" class="gap">
      <template #header>DDD 四边界分库拓扑</template>
      <el-table :data="data.databases" stripe>
        <el-table-column prop="role" label="限界上下文用途" width="160">
          <template #default="{ row }"><strong>{{ row.role }}</strong></template>
        </el-table-column>
        <el-table-column prop="name" label="数据库名" min-width="180">
          <template #default="{ row }"><code>{{ row.name }}</code></template>
        </el-table-column>
        <el-table-column label="标讯原文存放" width="160">
          <template #default="{ row }">
            <el-tag size="small" :type="row.holdsNotices ? 'primary' : 'info'" effect="plain">
              {{ row.holdsNotices ? "主存放库" : "不存放原文" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="建库状态" width="140">
          <template #default="{ row }">
            <el-tag size="small" :type="row.exists ? 'success' : 'info'">
              <span class="status-dot" :class="row.exists ? 'is-running' : 'is-idle'"></span>
              {{ row.exists ? "已建库" : data.online ? "尚未写入" : "未连接" }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-row v-if="data" :gutter="16" class="kpi-row">
      <el-col :xs="24" :md="10">
        <el-card shadow="never" style="width: 100%">
          <template #header>公告集合分表统计</template>
          <el-table :data="data.collections" empty-text="还没有公告表" stripe>
            <el-table-column prop="name" label="集合表名" min-width="180">
              <template #default="{ row }"><code>{{ row.name }}</code></template>
            </el-table-column>
            <el-table-column prop="count" label="文档条数" width="110" align="right">
              <template #default="{ row }">
                <strong :style="row.count ? 'color: #2563eb' : 'color: #94a3b8'">{{ row.count }}</strong>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
      <el-col :xs="24" :md="14">
        <el-card shadow="never" style="width: 100%">
          <template #header>
            <div class="bar">
              <span>最近 14 天入库趋势</span>
              <span style="font-size: 12px; color: #64748b; font-weight: 400">新插入 = 当天首次去重入库；采集保存 = 任务落库计数</span>
            </div>
          </template>
          <el-table :data="dayPage" max-height="360" empty-text="还没有按天汇总" stripe>
            <el-table-column prop="day" label="日期" width="150" />
            <el-table-column prop="inserted" label="新插入（去重后）">
              <template #default="{ row }">
                <strong :style="row.inserted ? 'color: #059669' : ''">{{ row.inserted }}</strong>
              </template>
            </el-table-column>
            <el-table-column prop="collected" label="任务采集保存" />
          </el-table>
          <div class="pager">
            <el-pagination
              v-model:current-page="dayPageNo"
              v-model:page-size="daySize"
              :total="(data.days || []).length"
              :page-sizes="[7, 14]"
              layout="total, sizes, prev, pager, next"
              background
              small
            />
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never">
      <template #header>
        <div class="bar">
          <span>历史采集批次记录（共 {{ runTotal }} 次）</span>
          <el-input
            v-model="runCrawler"
            clearable
            size="small"
            placeholder="按源头编号过滤，如 sgcc_ecp / csg_supply"
            style="width: 260px"
            @change="loadRuns(1)"
            @clear="loadRuns(1)"
          />
        </div>
      </template>
      <el-table v-loading="runsLoading" :data="runs" empty-text="还没有采集记录" stripe>
        <el-table-column prop="startedAt" label="开始时间" width="168" />
        <el-table-column prop="crawlerName" label="采集源头" min-width="180" show-overflow-tooltip />
        <el-table-column prop="channel" label="栏目" width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.channel || "全部栏目" }}</template>
        </el-table-column>
        <el-table-column prop="spanLabel" label="回看范围" width="115">
          <template #default="{ row }">{{ row.spanLabel || "默认范围" }}</template>
        </el-table-column>
        <el-table-column prop="status" label="执行结果" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="runStatusTag(row.status)">{{ runStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="saved" label="保存条数" width="90">
          <template #default="{ row }">
            <strong :style="row.saved ? 'color: #059669' : ''">{{ row.saved ?? 0 }}</strong>
          </template>
        </el-table-column>
        <el-table-column prop="error" label="备注与异常说明" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ formatRunNote(row.error || row.note) }}</template>
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

function runStatusLabel(status) {
  const map = {
    success: "成功",
    partial: "部分完成",
    failed: "失败",
    breaker: "熔断冷却",
    running: "运行中",
  }
  return map[status] || status || "—"
}

function runStatusTag(status) {
  const map = {
    success: "success",
    partial: "warning",
    failed: "danger",
    breaker: "info",
    running: "primary",
  }
  return map[status] || "info"
}

function formatRunNote(text) {
  if (!text) return "—"
  const firstLine = String(text).split("\n")[0].trim()
  return firstLine.replace(/^Message:\s*/i, "") || "—"
}

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
