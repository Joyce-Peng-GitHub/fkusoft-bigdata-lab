<template>
  <svg class="header-decoration" viewBox="0 0 1000 28" preserveAspectRatio="none" aria-hidden="true">
    <polyline points="0,5.6 180,5.6 200,11.2 250,11.2 270,16.8 720,16.8 750,11.2 800,11.2 820,5.6 1000,5.6" stroke-width="3" />
    <polyline points="300,22.4 700,22.4" stroke-width="2" />
  </svg>
</template>

<style scoped>
.header-decoration {
  display: block;
  width: 100%;
  height: 28px;
}

/* Keep the original decoration geometry responsive without scaling stroke widths.
   Each line reveals from its own center once per mount. App remounts this
   decoration on page navigation and manual/automatic refresh. The final frame
   stays fully open after completion and across metric changes or viewport resizes. */
polyline {
  fill: none;
  stroke: #3f96a5;
  vector-effect: non-scaling-stroke;
  animation: reveal-line 3s cubic-bezier(0.4, 1, 0.49, 0.98) forwards;
}

@keyframes reveal-line {
  from { clip-path: inset(-3px 50%) fill-box; }
  to { clip-path: inset(-3px 0) fill-box; }
}

@media (prefers-reduced-motion: reduce) {
  polyline { animation: none; }
}
</style>
