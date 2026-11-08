import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { authClient, type Account } from "../api/AuthClient";
import { onUnauthorized, UnauthorizedError } from "../api/http";

/** Who is logged in (ember_api's session). */
export const useAuthStore = defineStore("auth", () => {
  const account = ref<Account | null>(null);
  let loaded: Promise<void> | null = null;

  // Any 401 from ember_api means the session is gone.
  onUnauthorized(() => {
    account.value = null;
  });

  const permissions = computed(() => new Set(account.value?.permissions ?? []));

  // Mirrors ember_api: an unverified email holds no permissions, unless verification is switched off there.
  const needsVerification = computed(
    () => account.value !== null && !account.value.email_verified && account.value.email_verification_required !== false,
  );

  function hasPermission(name: string): boolean {
    return account.value !== null && !needsVerification.value && permissions.value.has(name);
  }

  /** Asks ember_api once per page load who is logged in (the router guard awaits it). */
  function ensureLoaded(): Promise<void> {
    loaded ??= authClient
      .me()
      .then((me) => {
        account.value = me;
      })
      .catch((err: unknown) => {
        if (!(err instanceof UnauthorizedError)) console.warn("legion_admin: /me failed", err);
        account.value = null;
      });
    return loaded;
  }

  async function login(username: string, password: string): Promise<void> {
    account.value = await authClient.login(username, password);
  }

  async function logout(): Promise<void> {
    try {
      await authClient.logout();
    } finally {
      account.value = null;
    }
  }

  return { account, needsVerification, hasPermission, ensureLoaded, login, logout };
});
