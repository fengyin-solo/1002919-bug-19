<template>
  <section class="page" data-module="accident">
    <header class="page-head">
      <div>
        <h2>事故管理</h2>
        <p class="page-desc">按期视图看板与事故台账共用同一份取数口径：结案即归档、移出待办，伤亡与损失未填的一律标待补。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记事故记录</button>
        <button class="btn" type="button" @click="exportRows">导出事故管理清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <section class="board">
      <header class="board-head">
        <strong>按期视图看板</strong>
        <span class="board-hint">点月份下钻到对应事故台账，重新进入会停在选中的月份</span>
      </header>
      <div v-if="boardError" class="board-error">
        <span>{{ boardError }}</span>
        <button class="btn" type="button" @click="loadBoard">重试</button>
      </div>
      <div v-else-if="board" class="board-body">
        <aside class="board-months">
          <button
            type="button"
            class="board-month"
            :class="{ active: selectedMonth === '' }"
            @click="selectMonth('')"
          >
            <span>全部月份</span>
            <span class="month-count">{{ board.summary.total }} 起</span>
          </button>
          <button
            v-for="item in board.months"
            :key="item.month"
            type="button"
            class="board-month"
            :class="{ active: selectedMonth === item.month }"
            @click="selectMonth(item.month)"
          >
            <span>{{ item.label }}</span>
            <span class="month-count">{{ item.total }} 起</span>
          </button>
        </aside>
        <div v-if="currentView" class="board-detail">
          <div class="board-cards">
            <div class="mini-card">
              <span class="stat-label">直接损失合计</span>
              <strong>{{ currentView.loss_total }} 万元</strong>
              <span v-if="currentView.loss_missing" class="tag-missing">{{ currentView.loss_missing }} 条损失待补</span>
            </div>
            <div class="mini-card">
              <span class="stat-label">待办 / 已结案</span>
              <strong>{{ currentView.pending }} / {{ currentView.closed }}</strong>
              <span v-if="currentView.casualty_missing" class="tag-missing">{{ currentView.casualty_missing }} 条伤亡待补</span>
            </div>
          </div>
          <div class="type-distribution">
            <h4>事故类型分布</h4>
            <div v-for="entry in currentView.type_distribution" :key="entry.type" class="type-row">
              <span class="type-name">{{ entry.type }}</span>
              <span class="type-bar"><i :style="{ width: typeWidth(entry.count) }" /></span>
              <span class="type-count">{{ entry.count }} 起</span>
            </div>
          </div>
          <div class="serious-block">
            <h4>重伤以上（单独挑出）</h4>
            <ul v-if="currentView.serious.length" class="serious-list">
              <li v-for="entry in currentView.serious" :key="String(entry.id)">
                <button class="link" type="button" @click="drillTo(entry)">
                  {{ entry['事故编号'] }} · {{ entry['事故设备'] }} · {{ entry['伤亡情况'] }} · {{ entry['发生时间'] || '时间待补' }}
                </button>
              </li>
            </ul>
            <p v-else class="board-empty">本段没有重伤以上事故</p>
          </div>
        </div>
        <p v-else class="board-empty">暂无事故数据</p>
      </div>
    </section>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <label class="filter-item">
        <span>事故状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
      <span v-if="selectedMonth" class="drill-chip">
        已下钻：{{ currentView?.label ?? selectedMonth }}
        <button class="link" type="button" @click="selectMonth('')">查看全部</button>
      </span>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>待办状态</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <span v-if="isMissingField(column, row[column])" class="tag-missing">待补</span>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td>
            <span v-if="row.pending" class="tag-pending">待办</span>
            <span v-else class="tag-closed">已归档</span>
          </td>
          <td class="row-actions">
            <template v-if="row.pending">
              <button
                v-for="action in actions"
                :key="action"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </template>
            <span v-else class="closed-note">已结案归档</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无事故管理数据，可先登记事故记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条事故管理记录</span>
      <span v-if="errorMessage" class="error-text">
        {{ errorMessage }}
        <button class="link" type="button" @click="reload">重试</button>
      </span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { fetchJson, request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

type BoardMonth = {
  month: string
  label: string
  total: number
  pending: number
  closed: number
  type_distribution: { type: string; count: number }[]
  loss_total: number
  loss_missing: number
  casualty_missing: number
  serious: Row[]
}

type Board = {
  summary: {
    total: number
    pending: number
    closed: number
    serious_total: number
    by_status: Record<string, number>
  }
  months: BoardMonth[]
}

const ENDPOINT = '/api/accident'
const MONTH_STORAGE_KEY = 'accident-board-month'
const columns = ["事故编号", "事故设备", "事故类型", "伤亡情况", "直接损失", "发生时间", "调查结论", "事故状态"]
const actions = ["上报事故", "开展调查", "结案归档"]
const statuses = ["待上报", "已上报", "调查中", "已结案"]
const MISSING_FIELDS = new Set(["伤亡情况", "直接损失"])
const FILTER_PARAM_MAP: Record<string, string> = { "事故编号": "keyword", "事故设备": "device", "事故类型": "accident_type" }

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const boardError = ref('')
const board = ref<Board | null>(null)
const selectedMonth = ref('')
const filters = ref<Record<string, string>>({})
const statusFilter = ref('')
const filterFields = columns.slice(0, 3)

const stats = computed(() => {
  const summary = board.value?.summary
  return [
    { label: '待办事故', value: summary?.pending ?? 0 },
    { label: '调查中事故', value: summary?.by_status?.['调查中'] ?? 0 },
    { label: '已结案归档', value: summary?.closed ?? 0 },
    { label: '重伤以上', value: summary?.serious_total ?? 0 },
  ]
})

// 选中某月时直接取该月分段；选「全部月份」时把各月聚合回来，口径与台账一致
const currentView = computed<BoardMonth | null>(() => {
  const data = board.value
  if (!data) return null
  if (selectedMonth.value) {
    return data.months.find((item) => item.month === selectedMonth.value) ?? null
  }
  if (!data.months.length) return null
  const typeCounts = new Map<string, number>()
  const view: BoardMonth = {
    month: '',
    label: '全部月份',
    total: 0,
    pending: 0,
    closed: 0,
    type_distribution: [],
    loss_total: 0,
    loss_missing: 0,
    casualty_missing: 0,
    serious: [],
  }
  for (const month of data.months) {
    view.total += month.total
    view.pending += month.pending
    view.closed += month.closed
    view.loss_total += month.loss_total
    view.loss_missing += month.loss_missing
    view.casualty_missing += month.casualty_missing
    view.serious.push(...month.serious)
    for (const entry of month.type_distribution) {
      typeCounts.set(entry.type, (typeCounts.get(entry.type) ?? 0) + entry.count)
    }
  }
  view.loss_total = Math.round(view.loss_total * 100) / 100
  view.type_distribution = [...typeCounts.entries()]
    .map(([type, count]) => ({ type, count }))
    .sort((a, b) => b.count - a.count || a.type.localeCompare(b.type))
  return view
})

const maxTypeCount = computed(() =>
  Math.max(1, ...(currentView.value?.type_distribution.map((entry) => entry.count) ?? [1])),
)

function typeWidth(count: number) {
  return `${Math.max(6, Math.round((count / maxTypeCount.value) * 100))}%`
}

function isMissingField(column: string, value: Row[string]) {
  return MISSING_FIELDS.has(column) && (value === null || value === undefined || String(value).trim() === '')
}

function selectMonth(month: string) {
  selectedMonth.value = month
  localStorage.setItem(MONTH_STORAGE_KEY, month)
  void reload()
}

function drillTo(entry: Row) {
  filters.value = { "事故编号": String(entry['事故编号'] ?? '') }
  void reload()
}

function resetFilters() {
  filters.value = {}
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '事故记录登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message ?? payload.detail ?? '事故管理动作未生效，请稍后重试')
    }
    await Promise.all([reload(), loadBoard()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '事故管理操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  for (const [field, value] of Object.entries(filters.value)) {
    const key = FILTER_PARAM_MAP[field]
    if (key && value.trim()) params.set(key, value.trim())
  }
  if (statusFilter.value) params.set('status', statusFilter.value)
  if (selectedMonth.value) params.set('month', selectedMonth.value)
  params.set('size', '200')
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      throw new Error('事故记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '事故管理列表读取失败'
  }
}

async function loadBoard() {
  boardError.value = ''
  try {
    const payload = await fetchJson<Board>(`${ENDPOINT}/board`)
    board.value = payload
    const keys = payload.months.map((item) => item.month)
    const stored = localStorage.getItem(MONTH_STORAGE_KEY)
    if (stored === null) {
      // 首次进入默认停在最近一个月
      selectedMonth.value = keys[0] ?? ''
    } else if (stored !== '' && !keys.includes(stored)) {
      // 记住的月份已不在数据里，回退到最近一个月
      selectedMonth.value = keys[0] ?? ''
    } else {
      selectedMonth.value = stored
    }
    localStorage.setItem(MONTH_STORAGE_KEY, selectedMonth.value)
  } catch (error) {
    boardError.value = error instanceof Error ? error.message : '按期视图看板读取失败'
  }
}

onMounted(async () => {
  await loadBoard()
  await reload()
})
</script>
