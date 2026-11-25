import { createRouter, createWebHistory } from "vue-router"
import CollectPage from "./domains/collect/CollectPage.vue"
import ExposurePage from "./domains/exposure/ExposurePage.vue"
import NodesPage from "./domains/nodes/NodesPage.vue"
import NoticesPage from "./domains/notices/NoticesPage.vue"
import OverviewPage from "./domains/overview/OverviewPage.vue"
import StoragePage from "./domains/storage/StoragePage.vue"

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/overview" },
    { path: "/overview", component: OverviewPage, meta: { title: "总览" } },
    { path: "/collect", component: CollectPage, meta: { title: "采集" } },
    { path: "/notices", component: NoticesPage, meta: { title: "公告" } },
    { path: "/api-catalog", component: ExposurePage, meta: { title: "开放接口" } },
    { path: "/storage", component: StoragePage, meta: { title: "数据库" } },
    { path: "/nodes", component: NodesPage, meta: { title: "节点" } },
  ],
})
