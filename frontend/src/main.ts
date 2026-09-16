import { createApp } from "vue";
import DataVVue3 from "@kjgl77/datav-vue3";
import App from "./App.vue";
import { applyTheme } from "./theme.js";

applyTheme();
createApp(App).use(DataVVue3).mount("#app");
