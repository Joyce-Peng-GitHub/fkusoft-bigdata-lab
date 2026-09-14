<script setup lang="ts">
import { onMounted, ref } from "vue";
import axios from "axios";

const status = ref("正在连接后端...");

onMounted(async () => {
  try {
    const response = await axios.get("/api/health");
    status.value = `服务正常：Hadoop ${response.data.hadoop} / PySpark ${response.data.pyspark}`;
  } catch {
    status.value = "后端服务暂不可用";
  }
});
</script>

<template>
  <main>
    <h1>大数据分析大屏</h1>
    <dv-border-box-1 class="status-panel">
      <p>{{ status }}</p>
    </dv-border-box-1>
  </main>
</template>

<style>
html,
body,
#app {
  width: 100%;
  min-height: 100%;
  margin: 0;
}

body {
  color: #f4f7fb;
  background: #101820;
  font-family: Inter, "Microsoft YaHei", sans-serif;
}

main {
  width: min(1200px, calc(100% - 32px));
  margin: 0 auto;
  padding: 32px 0;
}

h1 {
  margin: 0 0 24px;
  font-size: 28px;
  letter-spacing: 0;
}

.status-panel {
  width: 100%;
  height: 120px;
}

.status-panel p {
  display: grid;
  height: 100%;
  margin: 0;
  place-items: center;
}
</style>
