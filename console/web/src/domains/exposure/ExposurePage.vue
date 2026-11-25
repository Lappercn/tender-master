<template>
  <el-row :gutter="16">
    <el-col v-for="item in items" :key="item.id" :xs="24" :sm="12" :lg="8">
      <el-card
        class="gap net-card"
        :shadow="selectedNetId === item.id ? 'always' : 'hover'"
        :style="selectedNetId === item.id ? 'border-color: #409eff' : ''"
        @click="chooseNet(item)"
      >
        <template #header>
          <div class="bar">
            <span>{{ item.name }}</span>
            <el-tag :type="item.open ? 'success' : 'info'">{{ item.open ? "已开放" : "未开放" }}</el-tag>
          </div>
        </template>
        <p class="el-text">{{ item.summary }}</p>
        <p class="el-text" style="margin-top: 6px; font-size: 12px">
          源头（{{ (item.sources || []).length }}）：{{ sourceNames(item) || "暂无" }}
        </p>
      </el-card>
    </el-col>
  </el-row>

  <el-card v-if="opened" shadow="never">
    <template #header>
      <div class="bar">
        <span>{{ opened.name }} · 演练场</span>
        <div class="bar">
          <el-select v-model="selectedNetId" style="width: 180px" @change="onNetChange">
            <el-option v-for="item in openNets" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
          <el-tag type="success">已开放</el-tag>
        </div>
      </div>
    </template>
    <p>{{ opened.summary }}</p>
    <p class="el-text">来源：{{ sourceNames(opened) }}。这里调用的就是对外接口，和 Swagger 是同一条。</p>
    <el-form class="gap" :inline="true" @submit.prevent="run(1)">
      <el-form-item label="关键词">
        <el-input v-model="form.q" clearable placeholder="标题、采购人、项目编号" style="width: 220px" />
      </el-form-item>
      <el-form-item label="类型">
        <el-input v-model="form.noticeType" clearable placeholder="招标公告" style="width: 140px" />
      </el-form-item>
      <el-form-item label="地区">
        <el-input v-model="form.area" clearable placeholder="广东" style="width: 120px" />
      </el-form-item>
      <el-form-item label="源头">
        <el-select v-model="form.source" clearable placeholder="全部" style="width: 220px">
          <el-option v-for="source in opened.sources" :key="source.id" :label="source.name" :value="source.id" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" native-type="submit" :loading="loading">调用</el-button>
        <el-button @click="reset">清空条件</el-button>
      </el-form-item>
    </el-form>
    <el-alert v-if="error" class="gap" type="error" show-icon :closable="false" :title="error" />
    <p v-if="requestPath" class="request">GET {{ requestPath }}</p>
    <el-table v-loading="loading" :data="rows" empty-text="还没有调用，或这一页没有公告" @row-click="openDetail">
      <el-table-column prop="title" label="标题" min-width="240" show-overflow-tooltip />
      <el-table-column prop="source" label="来源" min-width="160" show-overflow-tooltip />
      <el-table-column prop="noticeType" label="类型" width="120" />
      <el-table-column prop="area" label="地区" width="90" />
      <el-table-column prop="createTime" label="时间" width="120" />
      <el-table-column label="操作" width="90" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click.stop="openDetail(row)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="pager">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="size"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        background
        @current-change="run"
        @size-change="run(1)"
      />
    </div>
  </el-card>

  <el-drawer v-model="detailOpen" title="公告详情" size="760px">
    <p v-if="detailPath" class="request">GET {{ detailPath }}</p>
    <el-alert v-if="detailError" type="error" show-icon :closable="false" :title="detailError" />
    <div v-loading="detailLoading">
      <NoticeDetail :detail="detail" />
    </div>
  </el-drawer>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue"
import { tell } from "../../shared/feedback.js"
import NoticeDetail from "../../shared/NoticeDetail.vue"
import { listNets, readNetNotice, searchNet } from "./api.js"

const items = ref([])
const selectedNetId = ref("power-grid")
const openNets = computed(() => items.value.filter(item => item.open))
const opened = computed(() => items.value.find(item => item.id === selectedNetId.value && item.open) || openNets.value[0] || null)
const form = reactive({ q: "", noticeType: "", area: "", source: "" })
const page = ref(1)
const size = ref(10)
const total = ref(0)
const rows = ref([])
const loading = ref(false)
const error = ref("")
const requestPath = ref("")
const detailOpen = ref(false)
const detailLoading = ref(false)
const detail = ref(null)
const detailError = ref("")
const detailPath = ref("")

function sourceNames(item) {
  return (item.sources || []).map(source => source.name).join("、")
}
function chooseNet(item) {
  if (!item?.open) return
  selectedNetId.value = item.id
  form.source = ""
  run(1)
}
function onNetChange() {
  form.source = ""
  run(1)
}
function reset() {
  form.q = ""
  form.noticeType = ""
  form.area = ""
  form.source = ""
  run(1)
}
async function run(nextPage) {
  if (!opened.value) return
  if (typeof nextPage === "number") page.value = nextPage
  loading.value = true
  error.value = ""
  const call = searchNet(opened.value.id, { ...form, page: page.value, size: size.value })
  requestPath.value = call.path
  try {
    const data = await call.run()
    rows.value = data.items || []
    total.value = data.total || 0
  } catch (err) {
    rows.value = []
    total.value = 0
    error.value = err.message
  } finally {
    loading.value = false
  }
}
async function openDetail(row) {
  if (!row?.contentId || !opened.value) return
  detailOpen.value = true
  detailLoading.value = true
  detail.value = null
  detailError.value = ""
  const call = readNetNotice(opened.value.id, row.contentId, row.crawlerId)
  detailPath.value = call.path
  try {
    detail.value = await call.run()
  } catch (err) {
    detailError.value = err.message
  } finally {
    detailLoading.value = false
  }
}
onMounted(async () => {
  try {
    const data = await listNets()
    items.value = data.items || []
    if (!items.value.some(item => item.id === selectedNetId.value && item.open)) {
      selectedNetId.value = openNets.value[0]?.id || "power-grid"
    }
    await run(1)
  } catch (err) {
    tell(err.message, "error")
  }
})
</script>

<style scoped>
.net-card { cursor: pointer; transition: border-color 0.2s; }
</style>
