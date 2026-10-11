import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import "./style.css";
import { HostBridge } from "./host/HostBridge";
import { HttpClient } from "./api/http";
import { AscensionClient } from "./api/AscensionClient";
import { useSessionStore } from "./stores/session";

const app = createApp(App);
const pinia = createPinia();
app.use(pinia);
const session = useSessionStore(pinia);
const fetchFn = window.fetch.bind(window);
session.bridge = new HostBridge({ fetchFn, win: window, parentWin: window.parent, hostOrigin: import.meta.env.VITE_EMBER_ORIGIN ?? "http://127.0.0.1:5173" });
session.client = new AscensionClient(new HttpClient(fetchFn, session.bridge, () => session.end()));
app.mount("#app");
