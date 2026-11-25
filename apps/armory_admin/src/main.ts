import { createApp } from "vue";
import { createPinia } from "pinia";
import "./style.css";
import { initTheme } from "@citadel/ui";
import App from "./App.vue";
import { router } from "./router";

initTheme("armory_admin.theme");

createApp(App).use(createPinia()).use(router).mount("#app");
