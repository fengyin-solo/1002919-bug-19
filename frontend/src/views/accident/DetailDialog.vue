<template>
  <div v-if="entry" class="modal-mask" @click.self="emit('close')">
    <div class="modal-card">
      <header class="modal-head">
        <div>
          <h3>{{ entry['事故编号'] }} 事故详情</h3>
          <p class="page-desc">伤亡与直接损失未填报的字段标成「待补」，不计入 0。</p>
        </div>
        <button class="btn ghost" type="button" @click="emit('close')">关闭</button>
      </header>
      <dl class="detail-grid">
        <div v-for="field in detailFields" :key="field" class="detail-item">
          <dt>{{ field }}</dt>
          <dd :class="{ 'todo-tag': displayValue(entry, field) === INCOMPLETE_TEXT }">
            {{ displayValue(entry, field) }}
          </dd>
        </div>
        <div class="detail-item">
          <dt>当前状态</dt>
          <dd>
            <span :class="['status-pill', isClosed(entry) ? 'closed' : 'pending']">
              {{ entry.status }}
            </span>
            <span v-if="isSevere(entry)" class="severe-tag">重伤以上</span>
          </dd>
        </div>
      </dl>
    </div>
  </div>
</template>

<script setup lang="ts">
import { INCOMPLETE_TEXT, displayValue, isClosed, isSevere, type AccidentRow } from './shared'

defineProps<{ entry: AccidentRow | null }>()
const emit = defineEmits<{ close: [] }>()

const detailFields = [
  '事故编号',
  '事故设备',
  '事故类型',
  '伤亡情况',
  '直接损失',
  '发生时间',
  '调查结论',
  '事故状态',
]
</script>
