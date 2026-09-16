<script setup lang="ts">
import { onMounted, onBeforeUnmount, watch, ref } from 'vue';
import * as echarts from 'echarts';
const props = defineProps<{ option: echarts.EChartsOption; label: string }>();
const element = ref<HTMLDivElement>();
let chart: echarts.ECharts | undefined;
let observer: ResizeObserver | undefined;
onMounted(() => {
  chart = echarts.init(element.value!);
  chart.setOption(props.option);
  observer = new ResizeObserver(() => chart?.resize());
  observer.observe(element.value!);
});
watch(() => props.option, option => chart?.setOption(option, true));
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose(); });
</script>
<template><div ref="element" class="chart" role="img" :aria-label="label" /></template>
<style scoped>.chart { width: 100%; height: 100%; flex: 1; min-height: 0; min-width: 0; }</style>
