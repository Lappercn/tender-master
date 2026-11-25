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
        <el-card shadow="hover">
          <el-statistic title="本机采集 / 浏览器" :value="data.crawlerCount || 0" :suffix="`/ ${data.browsers || 0}`" />
          <p class="el-text">当前节点：{{ data.currentNodeId || "local-1" }}</p>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card shadow="hover">
          <el-statistic title="分布式队列任务" :value="totalQueueTasks" />
          <p class="el-text">
            待领 {{ taskCounts.pending || 0 }} · 运行 {{ taskCounts.running || 0 }} · 完成 {{ taskCounts.success || 0 }} · 失败 {{ taskCounts.failed || 0 }}
          </p>
        </el-card>
      </el-col>
    </el-row>

    <el-card v-if="data" shadow="never" class="gap">
      <template #header>
        <div class="bar">
          <span>这台机器与守护进程（{{ data.currentNodeId }}）</span>
          <div class="bar">
            <el-tag :type="daemons.master?.running ? 'success' : 'info'">
              主节点调度器：{{ daemons.master?.running ? `运行中 (${daemons.master.pid})` : "未启动" }}
            </el-tag>
            <el-button
              v-if="!daemons.master?.running"
              size="small"
              type="primary"
              plain
              :loading="busy"
              @click="toggleDaemon('master', true)"
            >启动主节点</el-button>
            <el-button
              v-else
              size="small"
              type="danger"
              plain
              :loading="busy"
              @click="toggleDaemon('master', false)"
            >停止主节点</el-button>

            <el-tag :type="daemons.work?.running ? 'success' : 'info'">
              采集工作节点：{{ daemons.work?.running ? `运行中 (${daemons.work.pid})` : "未启动" }}
            </el-tag>
            <el-button
              v-if="!daemons.work?.running"
              size="small"
              type="primary"
              plain
              :loading="busy"
              @click="toggleDaemon('work', true)"
            >启动工作节点</el-button>
            <el-button
              v-else
              size="small"
              type="danger"
              plain
              :loading="busy"
              @click="toggleDaemon('work', false)"
            >停止工作节点</el-button>
          </div>
        </div>
      </template>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="处理器">{{ host.processor || "—" }}</el-descriptions-item>
        <el-descriptions-item label="本机正在采集">{{ runningText }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card v-if="data" shadow="never" class="gap">
      <template #header>
        <div class="bar">
          <span>分布式节点拓扑（1主多从 / 源头分流）</span>
          <el-button type="primary" size="small" @click="openAddNode">新增节点</el-button>
        </div>
      </template>
      <el-table :data="data.nodes" empty-text="还没有节点">
        <el-table-column prop="id" label="节点编号" width="150">
          <template #default="{ row }">
            <strong>{{ row.id }}</strong>
            <el-tag v-if="row.isLocal" size="small" type="success" style="margin-left: 6px">本机</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="row.online ? 'success' : 'info'">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="职责" width="170">
          <template #default="{ row }">{{ (row.roles || []).join("、") }}</template>
        </el-table-column>
        <el-table-column prop="accept" label="接收的采集源头" min-width="200" show-overflow-tooltip />
        <el-table-column label="浏览器策略" width="180">
          <template #default="{ row }">
            {{ row.browser === "selenium" ? "普通 Chrome" : "反检测 Chrome" }} · {{ row.headless ? "无头" : "有界面" }} · {{ row.fingerprint === "rotate" ? "轮换" : "固定" }}
          </template>
        </el-table-column>
        <el-table-column label="熔断保护" min-width="160">
          <template #default="{ row }">
            <template v-if="row.breakers && row.breakers.length">
              <el-tag
                v-for="b in row.breakers"
                :key="b.crawlerId"
                size="small"
                type="danger"
                style="margin-right: 4px"
              >{{ b.crawlerName }} (至{{ b.until }})</el-tag>
              <el-button link type="primary" size="small" @click="clearBreaker(row.id)">解除</el-button>
            </template>
            <span v-else class="el-text">正常</span>
          </template>
        </el-table-column>
        <el-table-column prop="lastSeen" label="最近心跳" width="165" />
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEditNode(row)">配置</el-button>
            <el-button
              v-if="data.nodes.length > 1"
              link
              type="danger"
              @click="removeNode(row)"
            >移除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="data" shadow="never">
      <template #header>
        <div class="bar">
          <span>集群栏目任务队列</span>
          <div class="bar">
            <el-button type="primary" size="small" :loading="busy" :disabled="!data.storageOnline" @click="dispatchAll">
              派发全量栏目任务
            </el-button>
            <el-button size="small" :loading="busy" :disabled="!data.storageOnline" @click="claimOnce">
              本机领取并执行 1 条
            </el-button>
            <el-button size="small" :loading="busy" :disabled="!data.storageOnline" @click="recoverTasks">
              回收超时任务
            </el-button>
            <el-button size="small" type="danger" plain :loading="busy" :disabled="!data.storageOnline" @click="clearTasks">
              清理已完成/待领
            </el-button>
          </div>
        </div>
      </template>
      <el-alert
        v-if="!data.storageOnline"
        class="gap"
        type="warning"
        show-icon
        :closable="false"
        title="MongoDB 未连通，分布式任务队列暂不可用（单机可直接去「采集」页启动源头，结果写本地暂存）"
      />
      <el-table :data="data.tasks || []" max-height="420" empty-text="队列里还没有任务。点击右上角「派发全量栏目任务」即可按节点分流投入。">
        <el-table-column prop="label" label="源头" min-width="180" show-overflow-tooltip />
        <el-table-column prop="channelLabel" label="栏目" min-width="130" show-overflow-tooltip />
        <el-table-column prop="targetNode" label="分配节点" width="130" />
        <el-table-column prop="nodeId" label="执行节点" width="130">
          <template #default="{ row }">{{ row.nodeId || "—" }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="taskTagType(row.status)">{{ taskStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="saved" label="保存" width="75" />
        <el-table-column prop="skipped" label="跳过" width="75" />
        <el-table-column prop="createdAt" label="投入时间" width="168" />
        <el-table-column label="说明" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.error || row.note || "—" }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogOpen" :title="editingNode ? '修改节点配置' : '新增分布式节点'" width="520px" append-to-body>
      <el-form label-width="96px">
        <el-form-item label="节点编号" required>
          <el-input v-model="form.node_id" :disabled="editingNode" placeholder="例如 worker-grid-1" />
        </el-form-item>
        <el-form-item label="节点职责" required>
          <el-checkbox-group v-model="form.roles">
            <el-checkbox value="master">主节点 (调度)</el-checkbox>
            <el-checkbox value="worker">采集节点 (执行)</el-checkbox>
            <el-checkbox value="storage">存储节点</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="接收源头">
          <el-radio-group v-model="acceptMode">
            <el-radio value="all">全部源头 (*)</el-radio>
            <el-radio value="custom">指定源头</el-radio>
            <el-radio value="none">不接采集任务</el-radio>
          </el-radio-group>
          <el-select
            v-if="acceptMode === 'custom'"
            v-model="form.accept"
            multiple
            placeholder="选择该节点负责的采集源头"
            style="width: 100%; margin-top: 8px"
          >
            <el-option
              v-for="src in data?.sources || []"
              :key="src.id"
              :label="`${src.name} (${src.netName})`"
              :value="src.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="运行方式">
          <el-radio-group v-model="form.headless">
            <el-radio :value="true">无头模式</el-radio>
            <el-radio :value="false">有界面</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="浏览器引擎">
          <el-radio-group v-model="form.browser">
            <el-radio value="undetected">反检测 Chrome</el-radio>
            <el-radio value="selenium">普通 Chrome</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="指纹策略">
          <el-radio-group v-model="form.fingerprint">
            <el-radio value="fixed">固定指纹</el-radio>
            <el-radio value="rotate">每次轮换</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="submitNode">保存配置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from "vue"
import { tell } from "../../shared/feedback.js"
import {
  clearClusterTasks,
  deleteNodeConfig,
  dispatchClusterTasks,
  nodeStatus,
  recoverClusterTasks,
  resetNodeBreaker,
  saveNodeConfig,
  startClusterDaemon,
  stopClusterDaemon,
  workOnce,
} from "./api.js"

const data = ref(null)
const busy = ref(false)
const dialogOpen = ref(false)
const editingNode = ref(false)
const acceptMode = ref("all")
const form = reactive({
  node_id: "",
  roles: ["worker"],
  accept: [],
  headless: true,
  browser: "undetected",
  fingerprint: "fixed",
})

const host = computed(() => data.value?.host || {})
const memory = computed(() => host.value.memory || {})
const daemons = computed(() => data.value?.daemons || {})
const taskCounts = computed(() => data.value?.taskCounts || {})
const totalQueueTasks = computed(() => Object.values(taskCounts.value).reduce((a, b) => a + Number(b || 0), 0))
const runningText = computed(() => {
  const rows = data.value?.crawlers || []
  if (!rows.length) return "没有"
  return rows.map(item => `${item.name}（PID ${item.pid}）`).join("、")
})
let timer = 0

function gb(bytes) {
  const value = Number(bytes) || 0
  if (!value) return "0 GB"
  return `${(value / 1024 ** 3).toFixed(1)} GB`
}
function taskStatusLabel(status) {
  const map = { pending: "待领取", running: "采集中", retry_wait: "等待重试", success: "已完成", failed: "失败" }
  return map[status] || status
}
function taskTagType(status) {
  const map = { pending: "info", running: "primary", retry_wait: "warning", success: "success", failed: "danger" }
  return map[status] || "info"
}
async function load() {
  data.value = await nodeStatus()
}
function tick() {
  if (document.visibilityState !== "visible") return
  load().catch(error => tell(error.message, "error"))
}
function openAddNode() {
  editingNode.value = false
  form.node_id = ""
  form.roles = ["worker"]
  form.accept = []
  form.headless = true
  form.browser = "undetected"
  form.fingerprint = "fixed"
  acceptMode.value = "all"
  dialogOpen.value = true
}
function openEditNode(row) {
  editingNode.value = true
  form.node_id = row.id
  form.roles = [...(row.rawRoles || ["worker"])]
  const rawAccept = row.rawAccept || []
  if (rawAccept.includes("*")) {
    acceptMode.value = "all"
    form.accept = []
  } else if (!rawAccept.length) {
    acceptMode.value = "none"
    form.accept = []
  } else {
    acceptMode.value = "custom"
    form.accept = [...rawAccept]
  }
  form.headless = row.headless !== false
  form.browser = row.browser || "undetected"
  form.fingerprint = row.fingerprint || "fixed"
  dialogOpen.value = true
}
async function submitNode() {
  if (!form.node_id.trim()) {
    tell("请填写节点编号", "error")
    return
  }
  if (!form.roles.length) {
    tell("请至少勾选一个节点职责", "error")
    return
  }
  let accept = ["*"]
  if (acceptMode.value === "none") accept = []
  else if (acceptMode.value === "custom") accept = form.accept
  await runAction(() =>
    saveNodeConfig({
      node_id: form.node_id.trim(),
      roles: form.roles,
      accept,
      headless: form.headless,
      browser: form.browser,
      fingerprint: form.fingerprint,
    })
  )
  dialogOpen.value = false
}
async function removeNode(row) {
  await runAction(() => deleteNodeConfig(row.id))
}
async function dispatchAll() {
  await runAction(() => dispatchClusterTasks({ lookbackDays: 14, maxPages: 40 }))
}
async function claimOnce() {
  await runAction(() => workOnce(data.value?.currentNodeId || ""))
}
async function recoverTasks() {
  await runAction(() => recoverClusterTasks())
}
async function clearTasks() {
  await runAction(() => clearClusterTasks())
}
async function clearBreaker(nodeId) {
  await runAction(() => resetNodeBreaker(nodeId))
}
async function toggleDaemon(role, start) {
  await runAction(() =>
    start ? startClusterDaemon(role, data.value?.currentNodeId) : stopClusterDaemon(role, data.value?.currentNodeId)
  )
}
async function runAction(fn) {
  busy.value = true
  try {
    const res = await fn()
    if (res?.ok === false) throw new Error(res.message || "操作未完成")
    tell(res?.message || "操作成功")
    await load()
  } catch (error) {
    tell(error.message, "error")
  } finally {
    busy.value = false
  }
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
