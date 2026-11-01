import { ApiError } from "./http";

export interface PollJobOptions<S> {
  fetch: () => Promise<S>;
  /** Handles a status; returns true once the job is finished. */
  onStatus: (status: S) => boolean;
  onFail: (error: unknown) => void;
  intervalMs: number;
  /** Consecutive failures tolerated before giving up (a 4xx always gives up). */
  maxFailures: number;
}

/** Polls a job without overlapping requests; returns a stop function. Stopping also
 * discards a response already in flight. */
export function pollJob<S>(options: PollJobOptions<S>): () => void {
  let stopped = false;
  let failures = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const stop = (): void => {
    stopped = true;
    clearTimeout(timer);
  };
  const poll = async (): Promise<void> => {
    try {
      const status = await options.fetch();
      if (stopped) return;
      failures = 0;
      if (options.onStatus(status)) return stop();
    } catch (error) {
      if (stopped) return;
      failures++;
      if ((error instanceof ApiError && error.status < 500) || failures >= options.maxFailures) {
        stop();
        options.onFail(error);
        return;
      }
    }
    timer = setTimeout(() => void poll(), options.intervalMs);
  };
  void poll();
  return stop;
}
