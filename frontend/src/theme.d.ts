import type { graphic } from 'echarts';

export const PALETTE: readonly string[];
export const HEATMAP_RAMP: readonly string[];
export const COLORS: Readonly<{
  transparent: string;
  page: string;
  pageGlow: string;
  panel: string;
  panelSolid: string;
  panelSheen: string;
  control: string;
  borderPanel: string;
  borderStrong: string;
  decoration: string;
  splitLine: string;
  textPrimary: string;
  textSecondary: string;
  textMuted: string;
  textFaint: string;
  accent: string;
  accentDim: string;
  accentGlow: string;
  error: string;
  errorBorder: string;
}>;
export const FONT_STACK: string;

export function withAlpha(hex: string, alpha: number): string;
export function areaGradient(hex: string, topAlpha?: number): graphic.LinearGradient;
export function barGradient(hex: string, horizontal?: boolean): graphic.LinearGradient;
export function applyTheme(): void;
