export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

type ApiRequestInit = RequestInit & { timeoutMs?: number };

export async function api<T>(path: string, init?: ApiRequestInit): Promise<T> {
  const { timeoutMs, ...requestInit } = init ?? {};
  const controller = timeoutMs === undefined ? undefined : new AbortController();
  const timeoutHandle = timeoutMs === undefined ? undefined : setTimeout(() => controller?.abort(), timeoutMs);

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...requestInit,
      signal: controller?.signal ?? requestInit.signal,
      headers: {
        "Content-Type": "application/json",
        ...(requestInit.headers || {})
      }
    });
    if (!res.ok) {
      const text = await res.text();
      let message = "";
      try {
        const parsed = JSON.parse(text);
        const detail = parsed.detail;
        if (typeof detail === "string") message = detail;
        if (detail?.message) message = detail.message;
      } catch {
        message = text;
      }
      if (message) throw new Error(message);
      throw new Error(`API ${res.status}`);
    }
    return res.json() as Promise<T>;
  } catch (error) {
    if (controller?.signal.aborted) {
      throw new Error("サーバーからの応答がありません。接続を確認して、もう一度お試しください。");
    }
    throw error;
  } finally {
    if (timeoutHandle !== undefined) clearTimeout(timeoutHandle);
  }
}

export function participantId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("participant_id");
}

export function requireParticipant(): string {
  const id = participantId();
  if (!id) {
    throw new Error("participant_idがありません。/startから開始してください。");
  }
  return id;
}
