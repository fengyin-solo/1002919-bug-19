<template>
  <section class="page">
    <header class="page-head">
      <div>
        <h2>运营概览</h2>
        <p class="page-desc">汇总各业务模块的关键指标，先看总量再看异常；事故的待处理与已结案同一套判定。</p>
      </div>
    </header>
    <div v-if="failed" class="retry-banner">
      <span>运营概览取数失败：{{ errorMessage }}</span>
      <button class="btn" type="button" :disabled="loading" @click="void loadOverview()">重试</button>
    </div>
    <template v-else>
      <div class="stat-row">
        <article v-for="card in cards" :key="card.label" class="stat-card">
          <span class="stat-label">{{ card.label }}</span>
          <strong class="stat-value">{{ card.value }}</strong>
        </article>
      </div>
      <table class="data-table">
        <thead>
          <tr><th>业务模块</th><th>今日新增</th><th>待处理</th><th>异常量</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in moduleRows" :key="row.name">
            <td>{{ row.name }}</td>
            <td>{{ row.created }}</td>
            <td>{{ row.pending }}</td>
            <td>{{ row.abnormal }}</td>
          </tr>
        </tbody>
      </table>
    </template>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson } from '@/api/client'

type Overview = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
}

const cards = ref<Overview['cards']>([])
const moduleRows = ref<Overview['modules']>([])
const failed = ref(false)
const loading = ref(false)
const errorMessage = ref('')

// 取数失败时保留上次数据并提示重试，而不是静默写 0
async function loadOverview() {
  loading.value = true
  failed.value = false
  errorMessage.value = ''
  try {
    const payload = await fetchJson<Overview>('/api/overview')
    cards.value = payload.cards
    moduleRows.value = payload.modules
  } catch (error) {
    failed.value = true
    errorMessage.value = error instanceof Error ? error.message : '运营概览取数失败'
  } finally {
    loading.value = false
  }
}

onMounted(loadOverview)
</script>
