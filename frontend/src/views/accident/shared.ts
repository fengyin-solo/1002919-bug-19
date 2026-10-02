/** 事故台账与按期看板共用的取数与展示口径。 */
import { computed, ref } from 'vue'

import { request } from '@/api/client'

export const ENDPOINT = '/api/accident'

export const COLUMNS = [
  '事故编号',
  '事故设备',
  '事故类型',
  '伤亡情况',
  '直接损失',
  '发生时间',
  '调查结论',
  '事故状态',
] as const

export const ACTIONS = ['上报事故', '开展调查', '结案归档'] as const
export const STATUSES = ['待上报', '已上报', '调查中', '已结案'] as const

/** 伤亡、损失没填时标成「待补」，而不是当成 0 */
export const INCOMPLETE_TEXT = '待补'
const INCOMPLETE_FIELDS = new Set(['伤亡情况', '直接损失'])

export type AccidentRow = Record<string, string | number | boolean | null>

export type Stats = {
  total: number
  pending: number
  closed: number
  severe: number
  by_status: Record<string, number>
}

export type MonthBucket = {
  month: string
  count: number
  severe_count: number
  loss_total: number
  loss_total_text: string
  loss_missing: number
  types: { type: string; count: number }[]
  items?: AccidentRow[]
  severe_items?: AccidentRow[]
}

export function displayValue(row: AccidentRow, field: string): string {
  const raw = row[field]
  const text = raw === null || raw === undefined ? '' : String(raw).trim()
  if (!text) {
    return INCOMPLETE_FIELDS.has(field) ? INCOMPLETE_TEXT : '—'
  }
  return text
}

export function isClosed(row: AccidentRow): boolean {
  return String(row.status ?? '') === '已结案'
}

export function isPending(row: AccidentRow): boolean {
  return !isClosed(row)
}

export function isSevere(row: AccidentRow): boolean {
  return row.severe === true
}

/** 把「接口请求失败 → 提示并可重试」收在一个加载器里，台账和看板共用。 */
export function useRetryableLoader<T>(load: () => Promise<T>) {
  const data = ref<T | null>(null)
  const loading = ref(false)
  const failed = ref(false)
  const errorMessage = ref('')

  async function run() {
    loading.value = true
    failed.value = false
    errorMessage.value = ''
    try {
      data.value = await load()
    } catch (error) {
      failed.value = true
      errorMessage.value = error instanceof Error ? error.message : '接口取数失败'
    } finally {
      loading.value = false
    }
  }

  return { data, loading, failed, errorMessage, run }
}

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) {
    throw new Error(`接口返回 ${response.status}，数据未更新`)
  }
  return (await response.json()) as T
}

/** 当前行允许执行的下一动作；结案后不再给流转按钮。 */
export function availableActions(row: AccidentRow): string[] {
  const status = String(row.status ?? '')
  const index = STATUSES.indexOf(status as (typeof STATUSES)[number])
  if (index < 0 || index >= ACTIONS.length) {
    return []
  }
  return index < ACTIONS.length ? [ACTIONS[index]] : []
}

export const statusOptions = computed(() => ['待处理', ...STATUSES])
