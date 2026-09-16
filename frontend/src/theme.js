import { graphic } from 'echarts';

/**
 * 大屏主题颜色的唯一来源。
 *
 * ECharts 绘制在 canvas 中，不能直接消费 CSS 自定义属性，因此颜色常量
 * 同时供图表配置直接引用，并由 applyTheme 写入 DOM 使用的 CSS 变量。
 * 修改配色时只需调整本文件，避免图表与页面样式逐渐产生色差。
 */
export const PALETTE = Object.freeze([
  '#34d88b',
  '#e8c35a',
  '#58d0d8',
  '#c98ee8',
  '#f28d7d',
  '#a8d95a',
]);

/** 热力图连续色带，从页面深色背景过渡到主题强调色。 */
export const HEATMAP_RAMP = Object.freeze([
  '#122b21',
  '#1d5c40',
  '#2aa268',
  '#34d88b',
]);

/** 语义颜色名称与下方 CSS 自定义属性一一对应。 */
export const COLORS = Object.freeze({
  transparent: 'transparent',
  page: '#0a1511',
  pageGlow: 'rgba(34, 94, 70, 0.45)',
  panel: 'rgba(13, 32, 26, 0.72)',
  panelSolid: '#0d201a',
  panelSheen: 'rgba(255, 255, 255, 0.05)',
  control: '#12291f',
  borderPanel: 'rgba(84, 138, 112, 0.35)',
  borderStrong: '#2e5c48',
  decoration: '#3f967a',
  splitLine: 'rgba(96, 148, 122, 0.22)',
  textPrimary: '#edf7ee',
  textSecondary: '#a8c7b4',
  textMuted: '#6f9682',
  textFaint: '#517a66',
  accent: '#34d88b',
  accentDim: 'rgba(52, 216, 139, 0.16)',
  accentGlow: 'rgba(52, 216, 139, 0.45)',
  error: '#ff8a7a',
  errorBorder: '#7a4b3b',
});

/** 页面字体虽不是颜色，也随主题一次注入，避免入口样式出现额外常量。 */
export const FONT_STACK = 'Inter, "Microsoft YaHei", sans-serif';

/**
 * 将六位十六进制颜色转换为带透明度的 rgba 颜色。
 *
 * @param {string} hex 六位十六进制颜色，例如 #34d88b。
 * @param {number} alpha 0 到 1 之间的透明度。
 * @returns {string} 可供 CSS 或 ECharts 使用的 rgba 颜色。
 * @throws {TypeError} 颜色格式或透明度不合法时抛出。
 */
export function withAlpha(hex, alpha) {
  const value = hex.replace('#', '');
  if (!/^[0-9a-fA-F]{6}$/.test(value)) {
    throw new TypeError(`Expected #rrggbb, got ${hex}`);
  }
  if (!Number.isFinite(alpha) || alpha < 0 || alpha > 1) {
    throw new TypeError(`Expected alpha between 0 and 1, got ${alpha}`);
  }
  const channel = (start) => Number.parseInt(value.slice(start, start + 2), 16);
  return `rgba(${channel(0)}, ${channel(2)}, ${channel(4)}, ${alpha})`;
}

/**
 * 创建自上而下逐渐透明的面积图填充。
 *
 * @param {string} hex 顶部使用的六位十六进制颜色。
 * @param {number} [topAlpha=0.3] 顶部透明度。
 * @returns {graphic.LinearGradient} ECharts 线性渐变。
 */
export function areaGradient(hex, topAlpha = 0.3) {
  return new graphic.LinearGradient(0, 0, 0, 1, [
    { offset: 0, color: withAlpha(hex, topAlpha) },
    { offset: 1, color: withAlpha(hex, 0.02) },
  ]);
}

/**
 * 创建柱状图渐变；横向条形图可沿水平方向衰减。
 *
 * @param {string} hex 柱体起始颜色。
 * @param {boolean} [horizontal=false] 是否使用水平方向渐变。
 * @returns {graphic.LinearGradient} ECharts 线性渐变。
 */
export function barGradient(hex, horizontal = false) {
  const [x, y, x2, y2] = horizontal ? [0, 0, 1, 0] : [0, 0, 0, 1];
  return new graphic.LinearGradient(x, y, x2, y2, [
    { offset: 0, color: hex },
    { offset: 1, color: withAlpha(hex, 0.3) },
  ]);
}

/**
 * 在应用挂载前把主题写入根元素，供所有 Vue 组件共享。
 *
 * @returns {void}
 */
export function applyTheme() {
  const variables = {
    '--color-transparent': COLORS.transparent,
    '--color-page': COLORS.page,
    '--color-page-glow': COLORS.pageGlow,
    '--color-panel': COLORS.panel,
    '--color-panel-solid': COLORS.panelSolid,
    '--color-panel-sheen': COLORS.panelSheen,
    '--color-control': COLORS.control,
    '--color-border-panel': COLORS.borderPanel,
    '--color-border-strong': COLORS.borderStrong,
    '--color-decoration': COLORS.decoration,
    '--color-split-line': COLORS.splitLine,
    '--color-text-primary': COLORS.textPrimary,
    '--color-text-secondary': COLORS.textSecondary,
    '--color-text-muted': COLORS.textMuted,
    '--color-text-faint': COLORS.textFaint,
    '--color-accent': COLORS.accent,
    '--color-accent-dim': COLORS.accentDim,
    '--color-accent-glow': COLORS.accentGlow,
    '--color-error': COLORS.error,
    '--color-error-border': COLORS.errorBorder,
    '--font-stack': FONT_STACK,
  };
  const root = document.documentElement.style;
  for (const [name, value] of Object.entries(variables)) {
    root.setProperty(name, value);
  }
}
