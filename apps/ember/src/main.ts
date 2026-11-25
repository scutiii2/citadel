import { createApp } from "vue";
import { createPinia } from "pinia";
import "./style.css";
import App from "./App.vue";
import { initTheme } from "@citadel/ui";
import { router } from "./router";

initTheme("ember_web.theme");
createApp(App).use(createPinia()).use(router).mount("#app");
