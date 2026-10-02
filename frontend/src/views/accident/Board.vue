<template>
  <section class="board">
    <div v-if="overview.failed.value" class="retry-banner">
      <span>看板总览取数失败：{{ overview.errorMessage.value }}</span>
      <button class="btn" type="button" :disabled="overview.loading.value" @click="void overview.run()">
        重试
      </button>
    </div>
    <div v-else-if="overview.loading.value" class="board-hint">正在加载月份分段…</div>

    <div v-else class="board-body">
      <aside class="month-list">
        <button
          v-for="bucket in months"
          :key="bucket.month"
          type="button"
          :class="['month-item', { active: bucket.month === selectedMonth }]"
          @click="emit('select', bucket.month)"
        >
          <strong>{{ bucket.month }}</strong>
          <span class="month-meta">{{ bucket.count }} 起 · 重伤以上 {{ bucket.severe_count }}</span>
          <span v-if="bucket.loss_missing > 0" class="month-todo">损失待补 {{ bucket.loss_missing }}</span>
        </button>
        <p v-if="!months.length" class="board-hint">暂无事故月份</p>
      </aside>

      <div class="month-panel">
        <div v-if="detail.failed.value" class="retry-banner">
          <span>{{ selectedMonth }} 明细取数失败：{{ detail.errorMessage.value }}</span>
          <button class="btn" type="button" :disabled="detail.loading.value" @click="void loadMonth(selectedMonth)">
            重试
          </button>
        </div>
        <div v-else-if="detail.loading.value" class="board-hint">正在加载 {{ selectedMonth }} 明细…</div>

        <template v-else-if="current">
          <header class="panel-head">
            <h3>{{ current.month }} 事故概览</h3>
            <span class="panel-sub">共 {{ current.count }} 起 · 直接损失合计 {{ current.loss_total_text }}
              <template v-if="current.loss_missing > 0">
                <span class="todo-inline">（{{ current.loss_missing }} 起损失待补，未计入合计）</span>
              </template>
            </span>
          </header>

          <div class="panel-columns">
            <article class="panel-block">
              <h4>事故类型分布</h4>
              <ul class="dist-list">
                <li v-for="item in current.types" :key="item.type">
                  <span class="dist-name">{{ item.type }}</span>
                  <span class="dist-bar">
                    <i :style="{ width: barWidth(item.count, current.count) }"></i>
                  </span>
                  <span class="dist-count">{{ item.count }} 起</span>
                </li>
              </ul>
            </article>

            <article class="panel-block severe-block">
              <h4>重伤以上事故（{{ current.severe_count }}）</h4>
              <p v-if="!current.severe_items?.length" class="board-hint">本月没有重伤以上事故</p>
              <ul v-else class="severe-list">
                <li v-for="row in current.severe_items" :key="String(row.id)">
                  <button class="link" type="button" @click="emit('open', row)">{{ row['事故编号'] }}</button>
                  <span>{{ row['事故设备'] }} · {{ row['事故类型'] }}</span>
                  <span class="severe-casualty">{{ row['伤亡情况'] || '待补' }}</span>
                </li>
              </ul>
            </article>
          </div>

          <article class="panel-block">
            <div class="drill-head">
              <h4>当月事故清单（点击下钻）</h4>
              <button class="btn ghost" type="button" @click="emit('ledger', current.month)">
                在台账中查看本月
              </button>
            </div>
            <table class="data-table">
              <thead>
                <tr><th>事故编号</th><th>事故设备</th><th>事故类型</th><th>伤亡情况</th><th>发生时间</th><th>状态</th></tr>
              </thead>
              <tbody>
                <tr v-for="row in current.items" :key="String(row.id)">
                  <td>
                    <button class="link" type="button" @click="emit('open', row)">{{ row['事故编号'] }}</button>
                  </td>
                  <td>{{ row['事故设备'] }}</td>
                  <td>{{ row['事故类型'] }}</td>
                  <td :class="{ 'todo-tag': displayValue(row, '伤亡情况') === INCOMPLETE_TEXT }">
                    {{ displayValue(row, '伤亡情况') }}
                  </td>
                  <td>{{ displayValue(row, '发生时间') }}</td>
                  <td>{{ row.status }}</td>
                </tr>
              </tbody>
            </table>
          </article>
        </template>
        <p v-else class="board-hint">请在左侧选择一个月份。</p>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'

import {
  ENDPOINT,
  INCOMPLETE_TEXT,
  displayValue,
  fetchJson,
  useRetryableLoader,
  type AccidentRow,
  type MonthBucket,
} from './shared'

const props = defineProps<{
  selectedMonth: string
}>()
const emit = defineEmits<{
  select: [month: string]
  open: [row: AccidentRow]
  ledger: [month: string]
}>()

const overview = useRetryableLoader<{ months: MonthBucket[] }>(() =>
  fetchJson<{ months: MonthBucket[] }>(`${ENDPOINT}/board`),
)

// 月份随点击切换，加载函数每次调用时从 props 取当前选中月
const detail = useRetryableLoader<MonthBucket>(() =>
  fetchJson<MonthBucket>(`${ENDPOINT}/board/${encodeURIComponent(props.selectedMonth)}`),
)

const months = computed(() => overview.data.value?.months ?? [])
const current = computed(() => detail.data.value)

function barWidth(count: number, total: number): string {
  if (!total) return '0%'
  return `${Math.round((count / total) * 100)}%`
}

async function loadMonth(month: string) {
  detail.data.value = null
  if (!month) return
  await detail.run()
}

// 重新进入或点击其他月份时，停在选中的那个月并重新下钻
watch(
  () => props.selectedMonth,
  (month) => {
    void loadMonth(month)
  },
)

// 首次进入没有记忆、或记住的月份已没有事故时，自动落到最近一个月
watch(
  months,
  (list) => {
    if (!list.length) return
    if (!list.some((bucket) => bucket.month === props.selectedMonth)) {
      emit('select', list[0].month)
    }
  },
  { immediate: true },
)

// 动作执行后由父组件通知刷新；看板与台账走同一份取数，天然一个样
function refresh() {
  void overview.run()
  void loadMonth(props.selectedMonth)
}

void overview.run()
void loadMonth(props.selectedMonth)

defineExpose({ refresh })
</script>
