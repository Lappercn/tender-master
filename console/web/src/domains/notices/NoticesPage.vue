<template>
  <el-card shadow="never">
    <template #header>
      <div class="bar">
        <span>公告</span>
        <el-button type="primary" @click="openCreate">补录</el-button>
      </div>
    </template>
    <el-alert
      class="gap"
      type="info"
      show-icon
      :closable="false"
      title="标题、链接和正文是采集当时记下的，不能在这里改。"
      description="可以改类型、地区、采购人、项目编号这些整理字段。删除前会再确认一次。"
    />
    <el-form class="gap" :inline="true" @submit.prevent="load(1)">
      <el-form-item label="关键词">
        <el-input v-model="form.q" clearable placeholder="标题、采购人、项目编号" style="width: 220px" />
      </el-form-item>
      <el-form-item label="类型">
        <el-input v-model="form.noticeType" clearable style="width: 140px" />
      </el-form-item>
      <el-form-item label="地区">
        <el-input v-model="form.area" clearable style="width: 120px" />
      </el-form-item>
      <el-form-item label="源头">
        <el-select v-model="form.source" clearable placeholder="全部" style="width: 220px">
          <el-option v-for="source in sources" :key="source.id" :label="source.name" :value="source.id" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" native-type="submit" :loading="loading">查询</el-button>
        <el-button @click="reset">重置</el-button>
      </el-form-item>
    </el-form>
    <el-table v-loading="loading" :data="rows" empty-text="没有公告。库没连通时先看上方提示。">
      <el-table-column prop="title" label="标题" min-width="240" show-overflow-tooltip />
      <el-table-column prop="source" label="来源" min-width="150" show-overflow-tooltip />
      <el-table-column prop="noticeType" label="类型" width="120" />
      <el-table-column prop="area" label="地区" width="90" />
      <el-table-column prop="createTime" label="时间" width="120" />
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openDetail(row)">查看</el-button>
          <el-button link type="primary" @click="openEdit(row)">修改</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
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
        @current-change="load"
        @size-change="load(1)"
      />
    </div>
  </el-card>

  <el-dialog v-model="editorOpen" :title="creating ? '补录公告' : '修改公告'" width="560px" :close-on-click-modal="false">
    <el-form label-width="88px">
      <template v-if="creating">
        <el-form-item label="源头" required>
          <el-select v-model="draft.sourceId" placeholder="选择源头" style="width: 100%">
            <el-option v-for="source in sources" :key="source.id" :label="source.name" :value="source.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="标题" required>
          <el-input v-model="draft.title" maxlength="200" show-word-limit />
        </el-form-item>
        <el-form-item label="链接" required>
          <el-input v-model="draft.url" placeholder="https://" />
        </el-form-item>
        <el-form-item label="日期" required>
          <el-date-picker v-model="draft.createTime" type="date" value-format="YYYY-MM-DD" placeholder="选择日期" style="width: 100%" />
        </el-form-item>
        <el-form-item label="项目编号">
          <el-input v-model="draft.projectCode" />
        </el-form-item>
        <el-form-item label="正文">
          <el-input v-model="draft.detailText" type="textarea" :rows="5" placeholder="可粘贴公告正文，用来识别地区和采购人" />
        </el-form-item>
      </template>
      <template v-else>
        <el-form-item label="标题"><span>{{ draft.title }}</span></el-form-item>
        <el-form-item label="类型"><el-input v-model="draft.noticeType" /></el-form-item>
        <el-form-item label="地区"><el-input v-model="draft.area" /></el-form-item>
        <el-form-item label="采购人"><el-input v-model="draft.purchaser" /></el-form-item>
        <el-form-item label="项目编号"><el-input v-model="draft.projectCode" /></el-form-item>
        <el-form-item label="状态"><el-input v-model="draft.projectStatus" /></el-form-item>
        <el-form-item label="预算"><el-input v-model="draft.budget" /></el-form-item>
        <el-form-item label="栏目"><el-input v-model="draft.category" /></el-form-item>
      </template>
    </el-form>
    <template #footer>
      <el-button @click="editorOpen = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>

  <el-drawer v-model="detailOpen" title="公告详情" size="760px">
    <div v-loading="detailLoading">
      <NoticeDetail :detail="detail" />
    </div>
  </el-drawer>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue"
import { confirmRemove, tell } from "../../shared/feedback.js"
import NoticeDetail from "../../shared/NoticeDetail.vue"
import { createNotice, deleteNotice, listCatalog, listNotices, readNotice, updateNotice } from "./api.js"

const sources = ref([])
const form = reactive({ q: "", noticeType: "", area: "", source: "" })
const page = ref(1)
const size = ref(10)
const total = ref(0)
const rows = ref([])
const loading = ref(false)
const saving = ref(false)
const editorOpen = ref(false)
const creating = ref(true)
const draft = reactive(emptyDraft())
const detailOpen = ref(false)
const detailLoading = ref(false)
const detail = ref(null)

function emptyDraft() {
  return {
    sourceId: "",
    title: "",
    url: "",
    createTime: "",
    projectCode: "",
    detailText: "",
    contentId: "",
    crawlerId: "",
    noticeType: "",
    area: "",
    purchaser: "",
    projectStatus: "",
    budget: "",
    category: "",
  }
}
function fillDraft(row) {
  Object.assign(draft, emptyDraft(), row || {})
}
async function load(nextPage) {
  if (typeof nextPage === "number") page.value = nextPage
  loading.value = true
  try {
    const data = await listNotices({ ...form, page: page.value, size: size.value })
    rows.value = data.items || []
    total.value = data.total || 0
  } catch (error) {
    rows.value = []
    total.value = 0
    tell(error.message, "error")
  } finally {
    loading.value = false
  }
}
function reset() {
  form.q = ""
  form.noticeType = ""
  form.area = ""
  form.source = ""
  load(1)
}
function openCreate() {
  creating.value = true
  fillDraft({ sourceId: sources.value[0]?.id || "" })
  editorOpen.value = true
}
async function openEdit(row) {
  try {
    const found = await readNotice(row.crawlerId, row.contentId)
    creating.value = false
    fillDraft(found)
    editorOpen.value = true
  } catch (error) {
    tell(error.message, "error")
  }
}
async function save() {
  saving.value = true
  try {
    if (creating.value) {
      const missing = []
      if (!draft.sourceId) missing.push("源头")
      if (!draft.title.trim()) missing.push("标题")
      if (!draft.url.trim()) missing.push("链接")
      if (!draft.createTime) missing.push("日期")
      if (missing.length) throw new Error(`${missing.join("、")}都要填`)
      const data = await createNotice({
        sourceId: draft.sourceId,
        title: draft.title.trim(),
        url: draft.url.trim(),
        createTime: draft.createTime,
        projectCode: draft.projectCode.trim(),
        detailText: draft.detailText,
      })
      tell(data.outcome === "spooled" ? "数据库未连通，已暂存到本机" : "公告已写入")
    } else {
      await updateNotice(draft.crawlerId, draft.contentId, {
        noticeType: draft.noticeType,
        area: draft.area,
        purchaser: draft.purchaser,
        projectCode: draft.projectCode,
        projectStatus: draft.projectStatus,
        budget: draft.budget,
        category: draft.category,
      })
      tell("已保存")
    }
    editorOpen.value = false
    await load(creating.value ? 1 : page.value)
  } catch (error) {
    tell(error.message, "error")
  } finally {
    saving.value = false
  }
}
async function remove(row) {
  try {
    await confirmRemove(row.title || "这条公告")
  } catch {
    return
  }
  try {
    await deleteNotice(row.crawlerId, row.contentId)
    tell("已删除")
    const last = rows.value.length === 1 && page.value > 1
    await load(last ? page.value - 1 : page.value)
  } catch (error) {
    tell(error.message, "error")
  }
}
async function openDetail(row) {
  detailOpen.value = true
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = await readNotice(row.crawlerId, row.contentId)
  } catch (error) {
    tell(error.message, "error")
    detailOpen.value = false
  } finally {
    detailLoading.value = false
  }
}
onMounted(async () => {
  try {
    const catalog = await listCatalog()
    const seen = new Set()
    const allSources = []
    for (const net of catalog.items || []) {
      for (const src of net.sources || []) {
        if (!seen.has(src.id)) {
          seen.add(src.id)
          allSources.push(src)
        }
      }
    }
    sources.value = allSources
  } catch (error) {
    tell(error.message, "error")
  }
  await load(1)
})
</script>
