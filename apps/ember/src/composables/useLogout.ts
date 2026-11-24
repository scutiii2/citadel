import { useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";

/** Ends the session, then leaves for the login page. */
export function useLogout(): () => Promise<void> {
  const auth = useAuthStore();
  const router = useRouter();
  return async () => {
    await auth.logout();
    await router.replace({ name: "login" });
  };
}
