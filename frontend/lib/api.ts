export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export class ApiError extends Error {
  status: number;
  code?: string;
  detail?: unknown;

  constructor(message: string, status: number, code?: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {})
    }
  });
  if (!res.ok) {
    const text = await res.text();
    let message = "";
    let code: string | undefined;
    let detail: unknown;
    try {
      const parsed = JSON.parse(text);
      detail = parsed.detail;
      if (typeof detail === "string") message = detail;
      if (detail && typeof detail === "object") {
        const errorDetail = detail as { message?: unknown; error_code?: unknown };
        if (typeof errorDetail.message === "string") message = errorDetail.message;
        if (typeof errorDetail.error_code === "string") code = errorDetail.error_code;
      }
    } catch {
      message = text;
    }
    throw new ApiError(message || `API ${res.status}`, res.status, code, detail);
  }
  return res.json() as Promise<T>;
}

type PendingIdempotentRequest = {
  key: string;
  body: string;
};

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
}

function pendingStorageKey(scope: string): string {
  return `idempotency_pending:${scope}`;
}

export function clearPendingIdempotency(scope: string): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(pendingStorageKey(scope));
}

export async function postIdempotent<T>(path: string, body: unknown, scope: string): Promise<T> {
  if (typeof window === "undefined") {
    return api<T>(path, { method: "POST", body: JSON.stringify(body) });
  }

  const bodyText = JSON.stringify(body);
  const storageKey = pendingStorageKey(scope);
  const storedText = window.sessionStorage.getItem(storageKey);
  let pending: PendingIdempotentRequest | null = null;
  if (storedText) {
    try {
      pending = JSON.parse(storedText) as PendingIdempotentRequest;
    } catch {
      pending = null;
    }
  }
  if (!pending || !pending.key) {
    pending = { key: newIdempotencyKey(), body: bodyText };
    window.sessionStorage.setItem(storageKey, JSON.stringify(pending));
  }

  try {
    const result = await api<T>(path, {
      method: "POST",
      body: pending.body,
      headers: { "Idempotency-Key": pending.key },
    });
    window.sessionStorage.removeItem(storageKey);
    return result;
  } catch (error) {
    if (
      error instanceof ApiError &&
      error.status >= 400 &&
      error.status < 500 &&
      error.code !== "idempotency_in_progress" &&
      error.code !== "idempotency_key_conflict"
    ) {
      window.sessionStorage.removeItem(storageKey);
    }
    throw error;
  }
}

export function participantId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("participant_id");
}

export function clearParticipantSession(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem("participant_id");
  localStorage.removeItem("display_code");
  localStorage.removeItem("pending_assignment_code");
  for (let index = window.sessionStorage.length - 1; index >= 0; index -= 1) {
    const key = window.sessionStorage.key(index);
    if (key?.startsWith("idempotency_pending:")) {
      window.sessionStorage.removeItem(key);
    }
  }
}

export function requireParticipant(): string {
  const id = participantId();
  if (!id) {
    throw new Error("participant_idがありません。/startから開始してください。");
  }
  return id;
}
