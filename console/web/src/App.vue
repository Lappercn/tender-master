<template>
  <el-container class="app">
    <el-aside class="aside" width="224px">
      <div class="logo">
        <div class="logo-badge">六</div>
        <div class="logo-text">
          <strong>六张网 · 招投标</strong>
          <span>智能采集与数据底座</span>
        </div>
      </div>
      <el-menu
        :default-active="route.path"
        router
        background-color="transparent"
        text-color="rgba(226,232,240,0.78)"
        active-text-color="#ffffff"
      >
        <el-menu-item index="/overview"><el-icon><Odometer /></el-icon><span>全局总览</span></el-menu-item>
        <el-menu-item index="/collect"><el-icon><Monitor /></el-icon><span>采集调度</span></el-menu-item>
        <el-menu-item index="/notices"><el-icon><Document /></el-icon><span>标讯检索</span></el-menu-item>
        <el-menu-item index="/api-catalog"><el-icon><Link /></el-icon><span>开放接口</span></el-menu-item>
        <el-menu-item index="/storage"><el-icon><Coin /></el-icon><span>数据存储</span></el-menu-item>
        <el-menu-item index="/nodes"><el-icon><Cpu /></el-icon><span>集群节点</span></el-menu-item>
      </el-menu>
      <div class="aside-footer">
        <span class="status-dot is-running"></span>
        <span>DDD 四边界底座运行中</span>
      </div>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div class="header-left">
          <h1>{{ title }}</h1>
          <span class="header-subtitle">{{ subtitle }}</span>
        </div>
        <div class="header-right">
          <span class="live-pill">
            <span class="status-dot is-running"></span>
            实时同步 (8s)
          </span>
          <el-button type="primary" plain size="small" tag="a" href="/docs" target="_blank">
            Swagger 接口文档 ↗
          </el-button>
        </div>
      </el-header>
      <el-main class="main">
        <RouterView v-slot="{ Component }">
          <transition name="fade-slide" mode="out-in">
            <component :is="Component" />
          </transition>
        </RouterView>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { Coin, Cpu, Document, Link, Monitor, Odometer } from "@element-plus/icons-vue"
import { computed } from "vue"
import { useRoute } from "vue-router"

const SUBTITLES = {
  "/overview": "实时掌控 15+ 政企与央国企采集源头、库存总量与主机负载",
  "/collect": "按源头配置回看范围、拟人化防封节奏、反检测内核与实时抓取流日志",
  "/notices": "跨平台标讯多维检索、6 级预算与防错配联系人详情抽屉、本地附件下载",
  "/api-catalog": "按「六张网」领域边界提供标准化 RESTful 接口，直连 CRM 与办公平台",
  "/storage": "MongoDB 分库分表监控、断网本地 Spool 暂存与历史采集运行记录",
  "/nodes": "1 主多从分布式节点拓扑、熔断保护器状态与集群栏目任务队列",
}

const route = useRoute()
const title = computed(() => route.meta.title || "总览")
const subtitle = computed(() => SUBTITLES[route.path] || "公开招投标公告解析与数据底座")
</script>
