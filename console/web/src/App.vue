<template>
  <el-container class="app">
    <el-aside class="aside" width="220px">
      <div class="logo">
        <strong>六张网</strong>
        <span>采集管理台</span>
      </div>
      <el-menu
        :default-active="route.path"
        router
        background-color="#001529"
        text-color="rgba(255,255,255,0.75)"
        active-text-color="#409eff"
      >
        <el-menu-item index="/overview"><el-icon><Odometer /></el-icon>总览</el-menu-item>
        <el-menu-item index="/collect"><el-icon><Monitor /></el-icon>采集</el-menu-item>
        <el-menu-item index="/notices"><el-icon><Document /></el-icon>公告</el-menu-item>
        <el-menu-item index="/api-catalog"><el-icon><Link /></el-icon>开放接口</el-menu-item>
        <el-menu-item index="/storage"><el-icon><Coin /></el-icon>数据库</el-menu-item>
        <el-menu-item index="/nodes"><el-icon><Cpu /></el-icon>节点</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <h1>{{ title }}</h1>
        <el-button tag="a" href="/docs" target="_blank">接口文档</el-button>
      </el-header>
      <el-main class="main">
        <RouterView />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { Coin, Cpu, Document, Link, Monitor, Odometer } from "@element-plus/icons-vue"
import { computed } from "vue"
import { useRoute } from "vue-router"

const route = useRoute()
const title = computed(() => route.meta.title || "总览")
</script>
