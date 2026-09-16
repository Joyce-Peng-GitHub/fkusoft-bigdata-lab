<script setup lang="ts">
import { onMounted, onBeforeUnmount, watch, ref } from 'vue';
import * as echarts from 'echarts';
const props = defineProps<{ option: echarts.EChartsOption; label: string; plotAspectRatio?: number }>();
// Constrain the plot, not the canvas: labels and the visual scale still need their
// original margins. A 24/7 plot makes a 24-column, 7-row heatmap use square cells.
// This opt-in supports a single grid with numeric pixel margins only.
function fittedOption(): echarts.EChartsOption {
  const grid = props.option.grid;
  if (!props.plotAspectRatio || !element.value || !grid || Array.isArray(grid)) return props.option;
  const { left, right, top, bottom } = grid;
  if (typeof left !== 'number' || typeof right !== 'number' || typeof top !== 'number' || typeof bottom !== 'number') return props.option;
  const availableWidth = Math.max(0, element.value.clientWidth - left - right);
  const availableHeight = Math.max(0, element.value.clientHeight - top - bottom);
  const width = Math.min(availableWidth, availableHeight * props.plotAspectRatio);
  const height = width / props.plotAspectRatio;
  return { ...props.option, grid: { ...grid,
    left: left + (availableWidth - width) / 2, right: right + (availableWidth - width) / 2,
    top: top + (availableHeight - height) / 2, bottom: bottom + (availableHeight - height) / 2,
  } };
}
const element = ref<HTMLDivElement>();
let chart: echarts.ECharts | undefined;
let observer: ResizeObserver | undefined;
onMounted(() => {
  chart = echarts.init(element.value!);
  chart.setOption(fittedOption());
  observer = new ResizeObserver(() => { chart?.resize(); chart?.setOption(fittedOption()); });
  observer.observe(element.value!);
});
watch(() => [props.option, props.plotAspectRatio], () => chart?.setOption(fittedOption(), true));
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose(); });
</script>
<template><div ref="element" class="chart" role="img" :aria-label="label" /></template>
<style scoped>.chart { width: 100%; height: 100%; flex: 1; min-height: 0; min-width: 0; }</style>
