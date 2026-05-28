export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

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
    throw new Error(text || `API ${res.status}`);
  }
  return res.json() as Promise<T>;
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
