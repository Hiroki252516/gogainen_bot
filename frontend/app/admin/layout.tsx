"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { API_BASE, api } from "@/lib/api";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const dialog = useRef<HTMLDialogElement>(null);
  const unlocked = useRef(false);
  const logoutPending = useRef(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [logoutRequired, setLogoutRequired] = useState(false);

  useEffect(() => {
    const lock = () => {
      if (logoutPending.current) return;
      unlocked.current = false;
      setAuthenticated(false);
    };
    const logout = () => {
      if (!unlocked.current && !logoutPending.current) return;
      unlocked.current = false;
      void fetch(`${API_BASE}/api/admin/auth/logout`, {
        method: "POST", credentials: "include", keepalive: true,
      }).catch(() => {});
    };
    const restore = (event: PageTransitionEvent) => { if (event.persisted) lock(); };
    window.addEventListener("pageshow", restore);
    window.addEventListener("admin-auth-required", lock);
    window.addEventListener("pagehide", logout);
    return () => {
      window.removeEventListener("pageshow", restore);
      window.removeEventListener("admin-auth-required", lock);
      window.removeEventListener("pagehide", logout);
      logout();
    };
  }, []);

  useEffect(() => {
    if (!authenticated && !dialog.current?.open) dialog.current?.showModal();
  }, [authenticated]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      await api("/api/admin/auth/login", { method: "POST", body: JSON.stringify({ password }) });
      setPassword("");
      unlocked.current = true;
      setAuthenticated(true);
    } catch (err) {
      setPassword("");
      setError(err instanceof Error ? err.message : "認証できませんでした。");
    } finally { setBusy(false); }
  }

  async function lock() {
    // Hide sensitive data immediately, even if the server cannot be reached.
    unlocked.current = false;
    logoutPending.current = true;
    setAuthenticated(false);
    setLogoutRequired(true);
    setPassword("");
    setBusy(true); setError("");
    try {
      await api("/api/admin/auth/logout", { method: "POST", timeoutMs: 5000 });
      logoutPending.current = false;
      setLogoutRequired(false);
    } catch {
      setError("画面はロックしましたが、認証解除を確認できません。接続を確認して再試行してください。");
    } finally { setBusy(false); }
  }

  if (authenticated) return <>
    <div className="admin-lock-bar"><button type="button" className="secondary" disabled={busy} onClick={lock}>管理画面をロック</button>
      {error ? <p role="alert" className="danger">{error}</p> : null}
    </div>
    {children}
  </>;

  return <main className="shell">
    <dialog ref={dialog} className="admin-password-dialog" aria-labelledby="admin-password-title"
      onCancel={(event) => { event.preventDefault(); router.replace("/start"); }}>
      <form className="stack" onSubmit={submit}>
        <h1 id="admin-password-title">管理画面のパスワード</h1>
        <label htmlFor="admin-password">パスワード</label>
        <input id="admin-password" name="password" type="password" autoComplete="current-password" autoFocus required
          maxLength={256} value={password} onChange={(event) => setPassword(event.target.value)} disabled={busy || logoutRequired} />
        {error ? <p className="danger" role="alert">{error}</p> : null}
        <div className="actions">
          <button type="submit" disabled={busy || logoutRequired}>{busy ? "確認中..." : "管理画面を開く"}</button>
          {logoutRequired ? <button type="button" className="secondary" disabled={busy} onClick={lock}>認証解除を再試行</button> : null}
          <button type="button" className="secondary" disabled={busy} onClick={() => router.replace("/start")}>キャンセル</button>
        </div>
      </form>
    </dialog>
  </main>;
}
