"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { API_BASE, api } from "@/lib/api";

type Participant = { participant_id: string; display_code: string; group_condition: string; current_step: string; completed_at: string | null };

export default function AdminPage() {
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [ai, setAi] = useState<any>(null);
  const [login, setLogin] = useState<any>(null);
  const [loginError, setLoginError] = useState("");

  useEffect(() => {
    api<{ participants: Participant[] }>("/api/admin/participants").then((data) => setParticipants(data.participants));
    api("/api/admin/evaluation-summary").then(setSummary);
    api("/api/admin/ai/status").then(setAi);
  }, []);

  async function startLogin(type: "chatgpt" | "chatgptDeviceCode") {
    setLoginError("");
    try {
      const result = await api("/api/admin/ai/login/start", {
        method: "POST",
        body: JSON.stringify({ type })
      });
      setLogin(result);
      if ((result as any).authUrl) {
        window.open((result as any).authUrl, "_blank", "noopener,noreferrer");
      }
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <AppShell step="管理画面">
      <div className="stack">
        <section className="panel stack">
          <h1>管理画面</h1>
          <div className="grid">
            <div className="notice">
              <strong>AI Backend</strong>
              <p>{ai ? `${ai.ai_backend} / ${ai.account_label}` : "確認中"}</p>
              {ai?.app_server_reachable === false ? <p className="danger">Codex app-serverに接続できません。</p> : null}
              {ai?.last_error ? <p className="muted">{ai.last_error}</p> : null}
              {ai?.logged_in === false ? (
                <div className="actions">
                  <button className="secondary" onClick={() => startLogin("chatgpt")}>
                    ChatGPTログイン
                  </button>
                  <button className="secondary" onClick={() => startLogin("chatgptDeviceCode")}>
                    デバイスコード
                  </button>
                </div>
              ) : null}
              {login?.verificationUrl ? (
                <p>
                  <a href={login.verificationUrl} target="_blank" rel="noreferrer">
                    認証ページ
                  </a>
                  {" / code: "}
                  <strong>{login.userCode}</strong>
                </p>
              ) : null}
              {loginError ? <p className="danger">{loginError}</p> : null}
            </div>
            {summary?.groups?.map((group: any) => (
              <div className="notice" key={group.group_condition}>
                <strong>{group.group_condition}</strong>
                <p>参加者: {group.participant_count}</p>
                <p>L0正答率: {formatRate(group.l0_correct_rate)}</p>
              </div>
            ))}
          </div>
          <div className="actions">
            {["participants", "attempts", "learner_states", "tutor_turns", "recurrence_events", "ai_call_logs", "evaluation_summary"].map((name) => (
              <a className="button secondary" href={`${API_BASE}/api/admin/export/${name}.csv`} key={name}>
                {name}.csv
              </a>
            ))}
          </div>
        </section>
        <section className="panel">
          <h2>被験者一覧</h2>
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>条件</th>
                <th>進捗</th>
                <th>完了</th>
              </tr>
            </thead>
            <tbody>
              {participants.map((p) => (
                <tr key={p.participant_id}>
                  <td>{p.display_code}</td>
                  <td>{p.group_condition}</td>
                  <td>{p.current_step}</td>
                  <td>{p.completed_at ? "完了" : "未完了"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </AppShell>
  );
}

function formatRate(value: number | null) {
  if (value === null || value === undefined) return "-";
  return `${Math.round(value * 100)}%`;
}
