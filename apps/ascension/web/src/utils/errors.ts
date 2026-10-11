/** Display text for anything a `catch` receives. */
export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

