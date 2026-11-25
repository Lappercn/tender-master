<template>
  <el-row :gutter="16">
    <el-col :xs="24" :md="8">
      <el-card shadow="never">
        <el-input v-model="keyword" clearable placeholder="按名称或编号筛选" />
        <el-table
          class="gap"
          style="margin-top: 12px"
          :data="paged"
          highlight-current-row
          empty-text="没有匹配的源头"
          @current-change="choose"
        >
          <el-table-column prop="name" label="源头" min-width="160" />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.running ? 'success' : 'info'">{{ row.running ? "采集中" : "未运行" }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
        <div class="pager">
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="size"
            :total="visible.length"
            :page-sizes="[10, 20, 50]"
            layout="total, prev, pager, next"
            background
            small
          />
        </div>
      </el-card>
    </el-col>
    <el-col :xs="24" :md="16">
      <el-empty v-if="!selected" description="选择左侧一个源头" />
      <template v-else>
        <el-card shadow="never" class="gap">
          <template #header>
            <div class="bar">
              <span>{{ selected.name }}</span>
              <div>
                <el-button type="primary" :disabled="selected.running || busy" @click="start">启动</el-button>
                <el-button type="danger" plain :disabled="!selected.running || busy" @click="askStop">关闭</el-button>
              </div>
            </div>
          </template>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="所属">{{ selected.netName || "新型电网" }}</el-descriptions-item>
            <el-descriptions-item label="状态">{{ selected.running ? `采集中，进程 ${selected.pid}` : "未运行" }}</el-descriptions-item>
            <el-descriptions-item label="栏目">{{ channelText || "—" }}</el-descriptions-item>
          </el-descriptions>
          <el-divider />
          <el-form label-width="88px" @submit.prevent="save">
            <el-form-item label="采集范围">
              <el-select v-model="profile.span" style="width: 220px">
                <el-option v-for="item in spans" :key="item.code" :label="item.label" :value="item.code" />
              </el-select>
            </el-form-item>
            <el-form-item label="采集节奏">
              <el-radio-group v-model="profile.pace">
                <el-radio v-for="item in paces" :key="item.code" :value="item.code" @click="openPace(item.code)">{{ item.label }}</el-radio>
              </el-radio-group>
              <p class="el-text">点一下「从容」或「正常」，查看这一档怎么停、连续多少次会多停一会儿。</p>
            </el-form-item>
            <el-form-item label="运行方式">
              <el-radio-group v-model="profile.headless">
                <el-radio :value="true">无头</el-radio>
                <el-radio :value="false">有界面</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="浏览器">
              <el-radio-group v-model="profile.browser">
                <el-radio value="undetected">反检测 Chrome</el-radio>
                <el-radio value="selenium">普通 Chrome</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="指纹">
              <el-radio-group v-model="profile.fingerprint">
                <el-radio value="fixed">固定</el-radio>
                <el-radio value="rotate">轮换</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" native-type="submit">保存设置</el-button>
              <el-button @click="applyAll">全部源头使用这个范围和节奏</el-button>
            </el-form-item>
          </el-form>
        </el-card>
        <el-card shadow="never" class="gap">
          <template #header>
            <div class="bar">
              <span>{{ selected.netName || "新型电网" }} · {{ selected.name }} 的进度</span>
            </div>
          </template>
          <el-table :data="progressRows" empty-text="还没有进度。启动后会按栏目更新。">
            <el-table-column prop="channelLabel" label="栏目" min-width="140" />
            <el-table-column prop="page" label="页" width="70" />
            <el-table-column prop="saved" label="保存" width="70" />
            <el-table-column prop="skipped" label="跳过" width="70" />
            <el-table-column prop="failed" label="失败" width="70" />
            <el-table-column prop="message" label="刚才" min-width="160" show-overflow-tooltip />
            <el-table-column prop="updatedAt" label="时间" width="170" />
          </el-table>
        </el-card>
        <el-card shadow="never">
          <template #header>
            <div class="bar">
              <span>采集记录</span>
              <div class="bar">
                <el-input v-model="logWord" clearable placeholder="标题或附件情况" style="width: 180px" />
                <el-select v-model="channel" clearable placeholder="全部栏目" style="width: 150px">
                  <el-option v-for="item in selected.channels || []" :key="item.code" :label="item.name" :value="item.name" />
                </el-select>
                <el-select v-model="logOutcome" clearable placeholder="全部结果" style="width: 120px">
                  <el-option v-for="item in outcomes" :key="item" :label="item" :value="item" />
                </el-select>
              </div>
            </div>
          </template>
          <el-table :data="pagedLogs" height="420" empty-text="还没有按标讯记下的记录。启动采集后，每条公告会留一行。">
            <el-table-column prop="time" label="时间" width="168" />
            <el-table-column prop="channel" label="栏目" width="120" show-overflow-tooltip />
            <el-table-column prop="outcome" label="结果" width="90" />
            <el-table-column prop="title" label="标讯" min-width="220" show-overflow-tooltip />
            <el-table-column prop="file" label="附件" min-width="220" show-overflow-tooltip />
          </el-table>
          <div class="pager">
            <el-pagination
              v-model:current-page="logPage"
              v-model:page-size="logSize"
              :total="shownLogs.length"
              :page-sizes="[10, 20, 50]"
              layout="total, sizes, prev, pager, next"
              background
              small
            />
          </div>
        </el-card>
      </template>
    </el-col>
  </el-row>
  <el-dialog v-model="paceOpen" :title="paceTitle" width="560px" append-to-body>
    <ol v-if="paceSteps.length" class="pace-steps">
      <li v-for="(line, index) in paceSteps" :key="index">{{ line }}</li>
    </ol>
    <p v-else>{{ paceHint || "这一档的停顿说明还没有加载出来。" }}</p>
  </el-dialog>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue"
import { confirmStop, tell } from "../../shared/feedback.js"
import { listSources, readLog, readProgress, saveBrowser, saveCollect, startSource, stopSource } from "./api.js"

const items = ref([])
const spans = ref([])
const paces = ref([])
const keyword = ref("")
const selectedId = ref("")
const profile = ref({ headless: true, browser: "undetected", fingerprint: "fixed", span: "14d", pace: "normal" })
const editing = ref(false)
const busy = ref(false)
const logText = ref("")
const channel = ref("")
const logWord = ref("")
const logOutcome = ref("")
const logPage = ref(1)
const logSize = ref(20)
const outcomes = ["已保存", "补附件", "跳过", "失败"]
const progressRows = ref([])
const paceOpen = ref(false)
const paceShown = ref(null)
const page = ref(1)
const size = ref(10)
let timer = 0

const visible = computed(() => {
  const text = keyword.value.trim().toLowerCase()
  return items.value.filter(item => !text || item.name.toLowerCase().includes(text) || item.id.includes(text))
})
const paged = computed(() => visible.value.slice((page.value - 1) * size.value, page.value * size.value))
const selected = computed(() => items.value.find(item => item.id === selectedId.value) || null)
const channelText = computed(() => (selected.value?.channels || []).map(item => item.name).join("、"))
const logRows = computed(() => {
  const rows = []
  for (const line of logText.value.split("\n")) {
    const mark = line.indexOf("标讯 ")
    if (mark < 0) continue
    const parts = line.slice(mark + 3).split(" | ")
    rows.push({
      time: line.slice(0, 19),
      channel: parts[0] || "",
      outcome: parts[1] || "",
      title: parts[2] || "",
      file: parts[3] || "",
    })
  }
  return rows.reverse()
})
const shownLogs = computed(() => {
  const word = logWord.value.trim()
  return logRows.value.filter(row => {
    if (channel.value && row.channel !== channel.value) return false
    if (logOutcome.value && row.outcome !== logOutcome.value) return false
    if (word && !`${row.title} ${row.file}`.includes(word)) return false
    return true
  })
})
const pagedLogs = computed(() => shownLogs.value.slice((logPage.value - 1) * logSize.value, logPage.value * logSize.value))
const paceTitle = computed(() => `${paceShown.value?.label || "采集"}的节奏`)
const paceSteps = computed(() => {
  if (paceShown.value?.steps?.length) return paceShown.value.steps
  return paceFallback[paceShown.value?.code] || []
})
const paceHint = computed(() => paceShown.value?.hint || "")
const paceFallback = {
  calm: [
    "翻页、进入栏目：每次随机停 4～9 秒。",
    "看完一条公告，再看下一条：随机停 3～7 秒。",
    "连续做了 6～10 次之后，额外再停 15～40 秒。连续次数和这次长停都是随机的，避免固定频率被网站拦住。",
    "打开一条公告时，点标题后停 1.5～3 秒，新窗口出来再停 1.5～3 秒，再向下扫 2～4 屏，每屏停 0.4～1.2 秒。这几下不计入上面的连续次数。",
    "单次停留满 8 秒，采集日志会记一行「停 N 秒，避开固定频率」。",
    "正在采集时改节奏不会立刻生效。先关闭，再启动，才按新的节奏走。",
  ],
  normal: [
    "翻页、进入栏目：每次随机停 2～5 秒。",
    "看完一条公告，再看下一条：随机停 1.8～4.5 秒。",
    "连续做了 8～14 次之后，额外再停 8～22 秒。连续次数和这次长停都是随机的，避免固定频率被网站拦住。",
    "打开一条公告时，点标题后停 1.5～3 秒，新窗口出来再停 1.5～3 秒，再向下扫 2～4 屏，每屏停 0.4～1.2 秒。这几下不计入上面的连续次数。",
    "单次停留满 8 秒，采集日志会记一行「停 N 秒，避开固定频率」。",
    "正在采集时改节奏不会立刻生效。先关闭，再启动，才按新的节奏走。",
  ],
}

function openPace(code) {
  paceShown.value = paces.value.find(item => item.code === code) || { code, label: code === "calm" ? "从容" : "正常" }
  paceOpen.value = true
}

function choose(row) {
  if (!row) return
  selectedId.value = row.id
  editing.value = false
  copyProfile()
}
function copyProfile() {
  const browser = selected.value?.browser || {}
  profile.value = {
    headless: browser.headless !== false,
    browser: browser.browser || "undetected",
    fingerprint: browser.fingerprint || "fixed",
    span: browser.span || "14d",
    pace: browser.pace || "normal",
  }
}
async function start() {
  await run(() => startSource(selectedId.value))
}
async function askStop() {
  try {
    await confirmStop(selected.value.name)
  } catch {
    return
  }
  await run(() => stopSource(selectedId.value))
}
async function applyAll() {
  editing.value = true
  try {
    await saveCollect({ span: profile.value.span, pace: profile.value.pace })
    tell("全部源头已改成这个采集范围和节奏")
    editing.value = false
    await load()
  } catch (error) {
    tell(error.message, "error")
  }
}
async function save() {
  editing.value = true
  try {
    await saveBrowser(selectedId.value, profile.value)
    tell("设置已保存。正在采集的源头，关闭后再启动才会换范围和节奏。")
    editing.value = false
    await load()
  } catch (error) {
    tell(error.message, "error")
  }
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
async function load() {
  const data = await listSources()
  items.value = data.items || []
  spans.value = data.spans || []
  paces.value = data.paces || []
  if (!items.value.some(item => item.id === selectedId.value)) {
    selectedId.value = items.value[0]?.id || ""
    editing.value = false
  }
  if (!editing.value) copyProfile()
  await loadLog()
}
async function loadLog() {
  if (!selectedId.value) return
  const data = await readLog(selectedId.value)
  logText.value = data.text || "还没有日志。启动一次采集后，输出会留在这里。"
  const progress = await readProgress(selectedId.value)
  progressRows.value = progress.items || []
}
function tick() {
  if (document.visibilityState !== "visible") return
  load().catch(error => tell(error.message, "error"))
}
watch(selectedId, () => {
  channel.value = ""
  logWord.value = ""
  logOutcome.value = ""
  logPage.value = 1
  copyProfile()
  loadLog().catch(error => tell(error.message, "error"))
})
watch([channel, logWord, logOutcome, logSize], () => {
  logPage.value = 1
})
watch(keyword, () => {
  page.value = 1
})
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

<style scoped>
.pace-steps { margin: 0; padding-left: 20px; line-height: 1.8; }
.pace-steps li + li { margin-top: 8px; }
</style>
