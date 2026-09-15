<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue';
import axios from 'axios';
import type { EChartsOption } from 'echarts';
import Chart from './components/Chart.vue';
import HeaderDecoration from './components/HeaderDecoration.vue';

type Row = Record<string, string | number>;
interface Dashboard {
  generated_at: string;
  overview: { sessions: number; energy: number; fees: number; stations: number; avg_duration: number };
  dimensions: Record<string, Row[]>;
  battery: { soc_band: number; samples: number; temperature: number; voltage_spread: number }[];
  quality: { source_rows: Record<string, number>; accepted_sessions: number; rejected_sessions: number; duplicates_removed: number; battery_accepted: number };
}
const data = ref<Dashboard>();
const loading = ref(false);
const error = ref('');
const metric = ref<'energy' | 'sessions'>('energy');
const unit = computed(() => metric.value === 'energy' ? 'kWh' : '单');
let timer: ReturnType<typeof setInterval>;
let controller: AbortController | undefined;
async function refresh() {
  if (loading.value) return;
  loading.value = true;
  error.value = '';
  controller = new AbortController();
  try {
    data.value = (await axios.get<Dashboard>('/api/dashboard', { timeout: 15000, signal: controller.signal })).data;
  } catch (cause) {
    if (!axios.isCancel(cause)) error.value = '暂时无法获取分析结果，请检查服务后重试。';
  } finally { loading.value = false; }
}
onMounted(() => { void refresh(); timer = setInterval(refresh, 60000); });
onBeforeUnmount(() => { clearInterval(timer); controller?.abort(); });
const number = (n: number, digits = 0) => n.toLocaleString('zh-CN', { maximumFractionDigits: digits });
// Format only at the presentation boundary: keep raw values for chart geometry,
// rankings and aggregation. Counts are integral; measured values use two decimals.
const metricNumber = (value: unknown) => number(Number(value), metric.value === 'sessions' ? 0 : 2);
const metricTooltip = (value: unknown) => `${metricNumber(value)} ${unit.value}`;
const axisNumber = (value: number) => number(value, 2);
const rows = (key: string) => data.value?.dimensions[key] ?? [];
const colors = ['#31e6c5', '#48a9ff', '#a195ff', '#ffc46c', '#ff789a'];
const base: EChartsOption = {
  color: colors, backgroundColor: 'transparent',
  textStyle: { color: '#9cb8ce', fontFamily: 'sans-serif' },
  tooltip: { trigger: 'axis', valueFormatter: metricTooltip },
  grid: { left: 55, right: 22, top: 35, bottom: 46 },
};
function category(key: string, field: string, type: 'bar' | 'line' = 'bar'): EChartsOption {
  const values = rows(key);
  return { ...base,
    xAxis: { type: 'category', data: values.map(r => String(r[field])), axisLabel: { hideOverlap: true } },
    yAxis: { type: 'value', name: unit.value, axisLabel: { formatter: axisNumber }, splitLine: { lineStyle: { color: '#163349' } } },
    series: [{ type, data: values.map(r => Number(r[metric.value])), smooth: true,
      ...(type === 'line' ? { areaStyle: { opacity: 0.13 } } : { barMaxWidth: 26 }) }],
  };
}
function donut(key: string, field: string): EChartsOption {
  return { ...base, tooltip: { trigger: 'item', valueFormatter: metricTooltip },
    legend: { bottom: 0, textStyle: { color: '#9cb8ce' } },
    series: [{ type: 'pie', radius: ['43%', '68%'], center: ['50%', '44%'],
      label: { color: '#cce3ef', formatter: '{b}\n{d}%' },
      data: rows(key).map(r => ({ name: String(r[field]), value: Number(r[metric.value]) })) }],
  };
}
const trend = computed(() => category('month', 'month', 'line'));
const hourly = computed(() => category('hour', 'hour', 'line'));
const platform = computed(() => donut('platform', 'platform'));
const facility = computed(() => donut('facility', 'facility'));
const duration = computed(() => category('duration', 'duration_band'));
const energy = computed(() => category('energy', 'energy_band'));
const location = computed(() => category('location', 'location'));
const vehicle = computed(() => donut('vehicle', 'vehicle'));
const weekday = computed<EChartsOption>(() => ({ ...category('weekday', 'weekday'),
  xAxis: { type: 'category', data: rows('weekday').map(r => ['一','二','三','四','五','六','日'][Number(r.weekday)-1]) },
}));
const stations = computed<EChartsOption>(() => {
  const top = [...rows('station')].sort((a,b) => Number(b[metric.value])-Number(a[metric.value])).slice(0,10).reverse();
  return { ...base, grid: { left: 78, right: 35, top: 20, bottom: 48 },
    graphic: [{ type: 'text', left: 0, bottom: 0, style: { text: '编号 / 贡献', fill: '#9cb8ce', fontSize: 10 } }],
    xAxis: { type: 'value', name: unit.value, axisLabel: { formatter: axisNumber } }, yAxis: { type: 'category', data: top.map(r => String(r.station)) },
    series: [{ type: 'bar', data: top.map(r => Number(r[metric.value])), barMaxWidth: 12,
      itemStyle: { borderRadius: [0, 5, 5, 0] } }],
  };
});
const comparison = computed<EChartsOption>(() => {
  const platforms = [...new Set(rows('platform_facility').map(r => String(r.platform)))];
  const facilities = [...new Set(rows('platform_facility').map(r => String(r.facility)))].sort();
  return { ...base, legend: { top: 0, textStyle: { color: '#9cb8ce' } },
    xAxis: { type: 'category', data: facilities.map(f => `类型 ${f}`) },
    yAxis: { type: 'value', name: unit.value, axisLabel: { formatter: axisNumber } },
    series: platforms.map(p => ({ name: p, type: 'bar', barMaxWidth: 20,
      data: facilities.map(f => Number(rows('platform_facility').find(r => r.platform === p && String(r.facility) === f)?.[metric.value] ?? 0)) })),
  };
});
const heatmap = computed<EChartsOption>(() => {
  const values = rows('weekday_hour');
  return { ...base, grid: { left: 40, right: 15, top: 20, bottom: 60 },
    tooltip: { position: 'top', formatter: params => {
      const item = Array.isArray(params) ? params[0]! : params;
      const [hour, day, value] = item.value as number[];
      return `周${['一','二','三','四','五','六','日'][day!]} ${hour}时<br/>${metricTooltip(value)}`;
    } },
    xAxis: { type: 'category', data: Array.from({length:24},(_,i) => `${i}时`), splitArea: { show: true } },
    yAxis: { type: 'category', data: ['周一','周二','周三','周四','周五','周六','周日'] },
    visualMap: { formatter: metricNumber, min: 0, max: Math.max(1,...values.map(r => Number(r[metric.value]))), calculable: true,
      orient: 'horizontal', left: 'center', bottom: 0, textStyle: { color: '#9cb8ce' },
      inRange: { color: ['#10293d','#17638a','#31e6c5'] } },
    series: [{ type: 'heatmap', data: Array.from({length:168},(_,i) => {
      const hour = i%24, day = Math.floor(i/24)+1;
      return [hour,day-1,Number(values.find(r => Number(r.hour)===hour && Number(r.weekday)===day)?.[metric.value] ?? 0)];
    }) }],
  };
});
const battery = computed<EChartsOption>(() => ({ ...base,
  tooltip: { trigger: 'item', formatter: params => {
    const item = Array.isArray(params) ? params[0]! : params;
    const [soc, temperature, samples] = item.value as number[];
    return `SOC 分段下界：${number(soc!)}%<br/>平均最高温度：${number(temperature!, 2)} ℃<br/>采样量：${number(samples!)} 条`;
  } },
  xAxis: { type: 'value', name: 'SOC 分段下界 (%)', min: 0, max: 100 },
  yAxis: { type: 'value', name: '平均最高温度 (℃)', axisLabel: { formatter: axisNumber } },
  series: [{ type: 'scatter', symbolSize: value => Math.max(10, Math.sqrt(Number(value[2]))*2),
    data: data.value?.battery.map(r => [r.soc_band, r.temperature, r.samples]) ?? [] }],
}));
const panels = computed(() => [
  { title:'月度充电趋势', note:'2014.11 — 2015.10', option:trend.value },
  { title:'平台构成', option:platform.value },
  { title:'站点贡献 TOP 10', option:stations.value },
  { title:'星期 × 小时分布', note:`交叉对比 01 · ${unit.value}`, option:heatmap.value, wide:true },
  { title:'平台 × 设施类型', note:'交叉对比 02 · 分组柱状', option:comparison.value },
  { title:'小时充电分布', note:'按订单开始时间', option:hourly.value },
  { title:'每周充电节律', option:weekday.value },
  { title:'设施类型构成', option:facility.value },
  { title:'充电时长分布', note:'按订单时长分段', option:duration.value },
  { title:'单次电量分布', note:'按订单电量分段', option:energy.value },
  { title:'地点对比', note:'地点编号', option:location.value },
  { title:'管理车辆标识', note:'0 / 1 为源数据标识', option:vehicle.value },
  { title:'电池 SOC 与温度', note:'气泡大小为采样量 · 独立遥测统计', option:battery.value },
]);
</script>

<template>
  <main>
    <header>
      <div class="brand"><span class="brand-mark">ϟ</span><div><h1>电动汽车充电站监测</h1></div></div>
      <div class="header-meta"><span class="live-dot" /> {{ data ? '分析数据已连接' : '等待数据连接' }}<br><small>HDFS · HIVE · SPARK · MYSQL</small></div>
    </header>
    <HeaderDecoration />
    <section class="toolbar" aria-label="展示控制">
      <p><span>{{ data ? '数据生成于 ' + new Date(data.generated_at).toLocaleString('zh-CN') : '加载中' }}</span></p>
      <div><label for="metric">分析指标</label> <select id="metric" v-model="metric"><option value="energy">充电电量 (kWh)</option><option value="sessions">订单数量 (单)</option></select><button @click="refresh" :disabled="loading">{{ loading ? '加载中…' : '刷新数据' }}</button></div>
    </section>
    <p v-if="error" class="message error" role="alert">{{ error }} {{ data ? '当前保留上次成功获取的数据。' : '' }}</p>
    <p v-if="!data && !error" class="message" role="status">正在读取分析结果…</p>
    <template v-if="data">
      <section class="kpis" aria-label="核心指标">
        <article v-for="item in [
          ['充电订单',number(data.overview.sessions),'单'],
          ['累计充电量',number(data.overview.energy,2),'kWh'],
          ['覆盖站点',number(data.overview.stations),'座'],
          ['累计费用',number(data.overview.fees,2),'源数据金额单位'],
          ['平均充电时长',number(data.overview.avg_duration,2),'小时'],
        ]" :key="item[0]"><span>{{ item[0] }}</span><strong>{{ item[1] }}</strong><small>{{ item[2] }}</small></article>
      </section>
      <section class="charts" aria-label="多维分析图表">
        <dv-border-box-12 v-for="panel in panels" :key="panel.title" class="panel" :class="{wide:panel.wide}" :color="['#20425e','#32cdb7']">
          <article><h2>{{ panel.title }}</h2><p v-if="panel.note" class="panel-note">{{ panel.note }}</p><Chart :option="panel.option" :label="panel.title" /></article>
        </dv-border-box-12>
      </section>
      <footer>
        <strong>数据质量</strong> · 有效订单 {{ number(data.quality.accepted_sessions) }} / {{ number(data.quality.source_rows.sessions ?? 0) }} · 异常隔离 {{ data.quality.rejected_sessions }} · 去重 {{ data.quality.duplicates_removed }} · 电池记录 {{ number(data.quality.battery_accepted) }}
      </footer>
    </template>
  </main>
</template>

<style>
:root{font-family:Inter,"Microsoft YaHei",sans-serif;color:#dfedf7;background:#07111e;font-synthesis:none;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 50% 0,#14344b80,transparent 65%),#07111e}button,select{font:inherit}main{max-width:1920px;margin:auto;padding:26px 32px}header{display:flex;align-items:center;justify-content:space-between;gap:20px}.brand{display:flex;align-items:center;gap:16px}.brand-mark{display:grid;place-items:center;width:48px;height:56px;color:#39e1bd;font-size:44px;border:1px solid #2a6972;border-radius:12px;background:#15343d}h1{font-size:27px;letter-spacing:4px;margin:0}.header-meta{font-size:13px;text-align:right;line-height:1.9;color:#a6c5d3}.header-meta small{font-size:9px;letter-spacing:2px;color:#54788e}.live-dot{display:inline-block;width:7px;height:7px;background:#36dfb7;border-radius:50%;box-shadow:0 0 10px #36dfb7;margin-right:5px}.toolbar{display:flex;justify-content:space-between;align-items:center;margin:10px 0 22px;gap:12px}.toolbar p{font-size:14px}.toolbar span{font-size:11px;color:#7395aa;margin-left:8px}.toolbar label{font-size:12px;color:#87a8be}select,button{background:#122b40;border:1px solid #2b4b62;border-radius:5px;padding:8px 12px;color:#d2eaf5;font-size:12px}button{margin-left:10px;cursor:pointer}button:disabled{opacity:.5;cursor:wait}.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:16px;margin-bottom:24px}.kpis article{padding:20px 22px;background:linear-gradient(115deg,#17374a90,#0c203580);border:1px solid #244256;border-top:2px solid #33c7b5;border-radius:5px}.kpis span{display:block;color:#8cabbf;font-size:12px}.kpis strong{display:block;font-size:32px;color:#ddf9f3;letter-spacing:1px;margin:9px 0 3px;font-variant-numeric:tabular-nums}.kpis small{color:#558ca3;font-size:10px}.charts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}.panel{min-width:0;background:#0c1c2d88;min-height:332px}.panel.wide{grid-column:span 2}.panel article{padding:20px 18px 12px}h2{font-size:14px;letter-spacing:1px;margin:0;border-left:3px solid #36d5bf;padding-left:9px}.panel-note{color:#597e97;font-size:10px;margin:7px 0 0 12px}footer{font-size:11px;color:#83a2b6;border-top:1px solid #1a3448;padding:22px 0 0;margin-top:24px;line-height:1.8}footer strong{color:#39c4ad}.message{padding:24px;border:1px solid #27475e;text-align:center}.error{color:#ffbc88;border-color:#81553b}select:focus-visible,button:focus-visible{outline:2px solid #31e6c5;outline-offset:3px}@media(min-width:1600px){.chart{height:290px!important}}@media(max-width:1000px){.charts{grid-template-columns:repeat(2,minmax(0,1fr))}.kpis{grid-template-columns:repeat(3,1fr)}.toolbar{align-items:flex-start;flex-direction:column}h1{font-size:22px}}@media(max-width:620px){main{padding:18px 12px}.header-meta{display:none}h1{font-size:19px;letter-spacing:1px}.kpis{grid-template-columns:repeat(2,1fr);gap:10px}.kpis article{padding:14px}.kpis strong{font-size:25px}.charts{grid-template-columns:1fr}.panel.wide{grid-column:auto}.toolbar span{display:block;margin:6px 0 0}}
</style>
