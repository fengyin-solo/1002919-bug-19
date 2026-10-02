<template>
  <section class="page" data-module="accident">
    <header class="page-head">
      <div>
        <h2>事故管理</h2>
        <p class="page-desc">维护事故记录，围绕事故编号、事故设备、事故类型、伤亡情况做登记、筛选与状态流转；结案即离开待处理。</p>
      </div>
      <div class="page-actions">
        <div class="tab-switch">
          <button
            type="button"
            :class="['tab-btn', { active: tab === 'ledger' }]"
            @click="switchTab('ledger')"
          >
            台账视图
          </button>
          <button
            type="button"
            :class="['tab-btn', { active: tab === 'board' }]"
            @click="switchTab('board')"
          >
            按期看板
          </button>
        </div>
        <button v-if="tab === 'ledger'" class="btn" type="button" @click="exportRows">导出事故管理清单</button>
      </div>
    </header>

    <div v-if="tab === 'ledger'" class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <template v-if="tab === 'ledger'">
      <form class="filter-bar" @submit.prevent="reload">
        <label class="filter-item">
          <span>关键字</span>
          <input v-model="keyword" placeholder="按事故编号或事故设备检索" />
        </label>
        <label class="filter-item">
          <span>状态</span>
          <select v-model="statusFilter">
            <option value="">全部状态</option>
            <option v-for="option in statusOptions" :key="option" :value="option">{{ option }}</option>
          </select>
        </label>
        <label v-if="monthFilter" class="filter-item">
          <span>月份</span>
          <span class="month-chip">{{ monthFilter }}<button class="link" type="button" @click="clearMonth">×</button></span>
        </label>
        <button class="btn primary" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
      </form>

      <div v-if="failed" class="retry-banner">
        <span>事故台账取数失败：{{ errorMessage }}（结案/归档数据未更新）</span>
        <button class="btn" type="button" :disabled="loading" @click="void reload()">重试</button>
      </div>
      <div v-else-if="statsFailed" class="retry-banner">
        <span>统计卡片取数失败：{{ statsErrorMessage }}</span>
        <button class="btn" type="button" @click="void loadStats()">重试</button>
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in columns" :key="column">{{ column }}</th>
            <th>可执行动作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="String(row.id)">
            <td v-for="column in columns" :key="column">
              <button v-if="column === '事故编号'" class="link" type="button" @click="openDetail(row)">
                {{ displayValue(row, column) }}
              </button>
              <span
                v-else
                :class="{ 'todo-tag': displayValue(row, column) === INCOMPLETE_TEXT }"
              >{{ displayValue(row, column) }}</span>
            </td>
            <td class="row-actions">
              <button
                v-for="action in availableActions(row)"
                :key="action"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
              <span v-if="isClosed(row)" class="closed-text">已归档</span>
            </td>
          </tr>
          <tr v-if="!rows.length && !failed">
            <td :colspan="columns.length + 1" class="empty-state">
              {{ loading ? '正在加载事故记录…' : '暂无符合条件的事故记录' }}
            </td>
          </tr>
        </tbody>
      </table>

      <footer class="page-foot">
        <span>共 {{ total }} 条事故记录</span>
        <span v-if="actionMessage" class="error-text">{{ actionMessage }}</span>
      </footer>
    </template>

    <AccidentBoard
      v-else
      ref="boardRef"
      :selected-month="selectedMonth"
      @select="selectMonth"
      @open="openDetail"
      @ledger="drillToLedger"
    />

    <DetailDialog :entry="detailEntry" @close="detailEntry = null" />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'
import AccidentBoard from './Board.vue'
import DetailDialog from './DetailDialog.vue'
import {
  COLUMNS,
  ENDPOINT,
  INCOMPLETE_TEXT,
  availableActions,
  displayValue,
  fetchJson,
  isClosed,
  statusOptions,
  type AccidentRow,
  type Stats,
} from './shared'

const TAB_STORAGE_KEY = 'accident.activeTab'
const MONTH_STORAGE_KEY = 'accident.selectedMonth'

const route = useRoute()
const router = useRouter()
const boardRef = ref<InstanceType<typeof AccidentBoard> | null>(null)

const columns = COLUMNS as unknown as string[]

// 选中月份优先取地址栏（链接可分享），其次本地记忆，保证重新进入停在那个月
const initialMonth =
  typeof route.query.month === 'string' && route.query.month
    ? route.query.month
    : localStorage.getItem(MONTH_STORAGE_KEY) ?? ''
const selectedMonth = ref(initialMonth)
const tab = ref(route.query.tab === 'board' || (!route.query.tab && localStorage.getItem(TAB_STORAGE_KEY) === 'board') ? 'board' : 'ledger')

const rows = ref<AccidentRow[]>([])
const total = ref(0)
const loading = ref(false)
const failed = ref(false)
const errorMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')
const monthFilter = ref(typeof route.query.month === 'string' ? route.query.month : '')
const actionMessage = ref('')

const stats = ref<Stats | null>(null)
const statsFailed = ref(false)
const statsErrorMessage = ref('')

const statCards = computed(() => [
  { label: '待处理事故', value: stats.value?.pending ?? '—' },
  { label: '已结案事故', value: stats.value?.closed ?? '—' },
  { label: '重伤以上事故', value: stats.value?.severe ?? '—' },
  { label: '事故总数', value: stats.value?.total ?? '—' },
])

function syncQuery() {
  const query: Record<string, string> = {}
  if (tab.value === 'board') {
    query.tab = 'board'
    if (selectedMonth.value) {
      query.month = selectedMonth.value
    }
  } else if (monthFilter.value) {
    query.month = monthFilter.value
  }
  void router.replace({ query })
}

function switchTab(next: 'ledger' | 'board') {
  tab.value = next
  localStorage.setItem(TAB_STORAGE_KEY, next)
  syncQuery()
  if (next === 'ledger') {
    void reload()
  } else {
    boardRef.value?.refresh()
  }
}

function selectMonth(month: string) {
  selectedMonth.value = month
  localStorage.setItem(MONTH_STORAGE_KEY, month)
  syncQuery()
}

function drillToLedger(month: string) {
  // 看板点月份下钻到对应事故：切台账并带上同一月份，两边取数完全一致
  selectedMonth.value = month
  monthFilter.value = month
  localStorage.setItem(MONTH_STORAGE_KEY, month)
  tab.value = 'ledger'
  localStorage.setItem(TAB_STORAGE_KEY, 'ledger')
  syncQuery()
  void reload()
}

function clearMonth() {
  monthFilter.value = ''
  localStorage.removeItem(MONTH_STORAGE_KEY)
  syncQuery()
  void reload()
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  monthFilter.value = ''
  localStorage.removeItem(MONTH_STORAGE_KEY)
  syncQuery()
  void reload()
}

async function loadStats() {
  statsFailed.value = false
  statsErrorMessage.value = ''
  try {
    stats.value = await fetchJson<Stats>(`${ENDPOINT}/stats`)
  } catch (error) {
    statsFailed.value = true
    statsErrorMessage.value = error instanceof Error ? error.message : '统计取数失败'
  }
}

async function reload() {
  loading.value = true
  failed.value = false
  errorMessage.value = ''
  actionMessage.value = ''
  const params = new URLSearchParams()
  if (keyword.value.trim()) {
    params.set('keyword', keyword.value.trim())
  }
  if (statusFilter.value) {
    params.set('status', statusFilter.value)
  }
  if (monthFilter.value) {
    params.set('month', monthFilter.value)
  }
  try {
    const payload = await fetchJson<{ items: AccidentRow[]; total: number }>(
      `${ENDPOINT}?${params.toString()}`,
    )
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    failed.value = true
    errorMessage.value = error instanceof Error ? error.message : '事故管理列表读取失败'
  } finally {
    loading.value = false
  }
}

const detailEntry = ref<AccidentRow | null>(null)

async function openDetail(row: AccidentRow) {
  try {
    detailEntry.value = await fetchJson<AccidentRow>(`${ENDPOINT}/${String(row.id)}`)
  } catch (error) {
    actionMessage.value = error instanceof Error ? error.message : '事故详情读取失败'
  }
}

async function runAction(action: string, row: AccidentRow) {
  actionMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${String(row.id)}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = (await response.json()) as { ok: boolean; message: string }
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '事故管理动作未生效，请稍后重试')
    }
    // 结案后立即从待处理挪走：列表、统计、看板三处同时按新状态重取
    await Promise.all([reload(), loadStats()])
    boardRef.value?.refresh()
  } catch (error) {
    actionMessage.value = error instanceof Error ? error.message : '事故管理操作失败'
  }
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

onMounted(() => {
  void reload()
  void loadStats()
})
</script>
