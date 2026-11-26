<template>
  <el-row :gutter="16" class="kpi-row">
    <el-col v-for="item in items" :key="item.id" :xs="24" :sm="12" :md="8">
      <el-card
        class="net-card"
        :class="{ 'is-selected': selectedNetId === item.id }"
        :shadow="selectedNetId === item.id ? 'always' : 'hover'"
        @click="chooseNet(item)"
      >
        <template #header>
          <div class="bar">
            <span style="font-size: 15px">{{ item.name }}</span>
            <el-tag size="small" :type="item.open ? 'success' : 'info'" effect="light">
              <span class="status-dot" :class="item.open ? 'is-running' : 'is-idle'"></span>
              {{ item.open ? "API 已开放" : "未开放" }}
            </el-tag>
          </div>
        </template>
        <p class="net-summary">{{ item.summary }}</p>
        <div class="net-sources">
          <el-tag
            v-for="src in item.sources || []"
            :key="src.id"
            size="small"
            type="info"
            effect="plain"
          >{{ src.name }}</el-tag>
        </div>
      </el-card>
    </el-col>
  </el-row>

  <el-card v-if="opened" shadow="never">
    <template #header>
      <div class="bar">
        <div style="display: flex; align-items: center; gap: 10px">
          <span>{{ opened.name }} · Open API 在线演练场（直连 CRM / 业务系统）</span>
          <el-tag size="small" type="success" effect="plain">GET /api/nets/{{ opened.id }}/notices</el-tag>
        </div>
        <div class="bar">
          <el-select v-model="selectedNetId" size="small" style="width: 170px" @change="onNetChange">
            <el-option v-for="item in openNets" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </div>
      </div>
    </template>
    <p style="margin: 0 0 6px; font-size: 13px; color: #334155">{{ opened.summary }}</p>
    <p class="el-text" style="font-size: 12px; color: #64748b; margin-top: 0">
      聚合源头：{{ sourceNames(opened) }}。下方调用的即为对外标准 RESTful 接口，可直接同步至企业 CRM 或办公机器人。
    </p>
    <el-form class="gap" style="margin-top: 14px" :inline="true" @submit.prevent="run(1)">
      <el-form-item label="关键词">
        <el-input v-model="form.q" clearable placeholder="标题、采购人、项目编号" style="width: 210px" />
      </el-form-item>
      <el-form-item label="类型">
        <el-input v-model="form.noticeType" clearable placeholder="如：招标公告" style="width: 140px" />
      </el-form-item>
      <el-form-item label="地区">
        <el-input v-model="form.area" clearable placeholder="如：广东" style="width: 120px" />
      </el-form-item>
      <el-form-item label="源头">
        <el-select v-model="form.source" clearable placeholder="当前网全部源头" style="width: 210px">
          <el-option v-for="source in opened.sources" :key="source.id" :label="source.name" :value="source.id" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" native-type="submit" :loading="loading">发起 API 调用</el-button>
        <el-button @click="reset">清空条件</el-button>
      </el-form-item>
    </el-form>
    <el-alert v-if="error" class="gap" type="error" show-icon :closable="false" :title="error" />
    <p v-if="requestPath" class="request">GET {{ requestPath }}</p>
    <el-table v-loading="loading" :data="rows" empty-text="还没有调用，或这一页没有公告" stripe @row-click="openDetail">
      <el-table-column prop="title" label="标讯标题" min-width="250" show-overflow-tooltip />
      <el-table-column prop="source" label="来源平台" min-width="150" show-overflow-tooltip />
      <el-table-column prop="noticeType" label="类型" width="115">
        <template #default="{ row }">
          <el-tag v-if="row.noticeType" size="small" effect="light">{{ row.noticeType }}</el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column prop="area" label="地区" width="100" show-overflow-tooltip />
      <el-table-column prop="createTime" label="发布日期" width="115" />
      <el-table-column label="操作" width="85" fixed="right">
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

  <el-drawer v-model="detailOpen" title="API 响应标讯详情" size="780px">
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
.net-card {
  width: 100%;
  cursor: pointer;
  display: flex;
  flex-direction: column;
}
.net-card.is-selected {
  border-color: #2563eb !important;
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.15) !important;
}
.net-summary {
  margin: 0 0 12px;
  font-size: 13px;
  color: #475569;
  line-height: 1.6;
}
.net-sources {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>
