<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import axios from 'axios';
import type { EChartsOption } from 'echarts';
import Chart from './Chart.vue';

interface Point { date: string; energy: number; sessions: number }
interface Forecast { generated_at: string; history_end: string; history: Point[]; forecast: Point[] }
const props = defineProps<{ metric: 'energy' | 'sessions'; refreshKey: number }>();
const data = ref<Forecast>();
const error = ref('');
const loading = ref(false);
let controller: AbortController | undefined;
// Forecast readiness is independent of analytics readiness. Keep the last good
// forecast visible after a failed refresh and cancel superseded requests.
watch(() => props.refreshKey, async () => {
  controller?.abort();
  const request = new AbortController();
  controller = request;
  loading.value = true;
  error.value = '';
  try {
    data.value = (await axios.get<Forecast>('/api/ml/forecast', {
      timeout: 15000, signal: request.signal,
    })).data;
  } catch (cause) {
    if (!axios.isCancel(cause)) error.value = '暂时无法获取预测结果，请确认预测任务已完成后刷新。';
  } finally {
    if (controller === request) loading.value = false;
  }
}, { immediate: true });
onBeforeUnmount(() => controller?.abort());
const unit = computed(() => props.metric === 'energy' ? 'kWh' : '单');
const option = computed<EChartsOption>(() => {
  const history = data.value?.history ?? [];
  const future = data.value?.forecast ?? [];
  return {
    color: ['#31e6c5', '#ffc46c'],
    textStyle: { color: '#9cb8ce' },
    tooltip: { trigger: 'axis', valueFormatter: value => value == null ? '—' :
      `${Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })} ${unit.value}` },
    legend: { top: 8, textStyle: { color: '#9cb8ce' } },
    grid: { left: 65, right: 24, top: 60, bottom: 40 },
    xAxis: { type: 'category', data: [...history, ...future].map(row => row.date), axisLabel: { hideOverlap: true } },
    yAxis: { type: 'value', name: unit.value, splitLine: { lineStyle: { color: '#163349' } } },
    // Anchor the dashed forecast at the last actual value to connect the two
    // periods. Earlier historical points remain absent from the forecast series.
    series: [
      { name: '历史实际', type: 'line', data: [...history.map(row => row[props.metric]), ...future.map(() => null)] },
      { name: '模型预测', type: 'line', lineStyle: { type: 'dashed' },
        data: [...history.map((row, index) => index === history.length - 1 ? row[props.metric] : null), ...future.map(row => row[props.metric])] },
    ],
  };
});
</script>

<template>
  <section class="forecast-panel" aria-label="历史与预测">
    <h2>历史与预测</h2>
    <p v-if="error" role="alert">{{ error }} {{ data ? '当前保留上次成功获取的预测结果。' : '' }}</p>
    <p v-else-if="loading && !data" role="status">预测结果加载中…</p>
    <Chart v-if="data" :option="option" label="历史实际与机器学习预测" />
  </section>
</template>

<style scoped>
.forecast-panel{margin:0 0 24px;padding:20px 18px;background:#0c1c2d88;border:1px solid #20425e;border-radius:6px;min-width:0}
p{font-size:12px;color:#9cb8ce;line-height:1.7}
p[role=alert]{color:#ffbc88}
</style>
