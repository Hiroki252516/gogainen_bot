"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { API_BASE, api } from "@/lib/api";

type Participant = { participant_id: string; display_code: string; group_condition: string; current_step: string; completed_at: string | null };
type Diagnosis = {
  observation_id: string;
  display_code: string;
  participant_completed: boolean;
  term_label: string;
  source_phase: string;
  diagnosed_status: string;
  primary_misconception_type: string | null;
  diagnosis_confidence: number | null;
  diagnosis_evidence: string | null;
  transition_type: string | null;
  applied_strategy: string | null;
  requires_manual_review: boolean;
  is_manual_override: boolean;
};

export default function AdminPage() {
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [ai, setAi] = useState<any>(null);
  const [login, setLogin] = useState<any>(null);
  const [loginError, setLoginError] = useState("");
  const [diagnoses, setDiagnoses] = useState<Diagnosis[]>([]);
  const [overrideDrafts, setOverrideDrafts] = useState<Record<string, { status: string; primary: string; reason: string }>>({});
  const [adminError, setAdminError] = useState("");

  useEffect(() => {
    api<{ participants: Participant[] }>("/api/admin/participants").then((data) => setParticipants(data.participants));
    api("/api/admin/evaluation-summary").then(setSummary);
    api("/api/admin/ai/status").then(setAi);
    api<{ diagnoses: Diagnosis[] }>("/api/admin/diagnoses").then((data) => setDiagnoses(data.diagnoses));
  }, []);

  async function overrideDiagnosis(row: Diagnosis) {
    const draft = overrideDrafts[row.observation_id] || {
      status: row.diagnosed_status,
      primary: row.primary_misconception_type || "",
      reason: ""
    };
    if (!draft.reason.trim()) {
      setAdminError("修正理由を入力してください。");
      return;
    }
    setAdminError("");
    try {
      await api(`/api/admin/diagnoses/${row.observation_id}/override`, {
        method: "POST",
        body: JSON.stringify({
          diagnosed_status: draft.status,
          primary_misconception_type: draft.primary || null,
          reason: draft.reason,
          actor: "researcher"
        })
      });
      const refreshed = await api<{ diagnoses: Diagnosis[] }>("/api/admin/diagnoses");
      setDiagnoses(refreshed.diagnoses);
      setOverrideDrafts((current) => ({ ...current, [row.observation_id]: { ...draft, reason: "" } }));
    } catch (err) {
      setAdminError(err instanceof Error ? err.message : String(err));
    }
  }

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
                <p>再テスト正答率: {formatRate(group.retest_score)}</p>
                <p>同種誤答再発率: {formatRate(group.same_misconception_recurrence_rate)}</p>
                <p>前提用語通過率: {formatRate(group.prerequisite_pass_rate)}</p>
                <p>概念理解通過率: {formatRate(group.concept_pass_rate)}</p>
                <p>Phase1通過率: {formatRate(group.concept_phase1_pass_rate)}</p>
                <p>Phase2成功率: {formatRate(group.concept_phase2_success_rate)}</p>
                <p>Phase2再支援後成功率: {formatRate(group.phase2_after_retry_success_rate)}</p>
              </div>
            ))}
          </div>
          <div className="actions">
            {[
              "participants",
              "participant_surveys",
              "term_assignments",
              "attempts",
              "learner_states",
              "learning_sessions",
              "prerequisite_terms",
              "term_understanding_attempts",
              "concept_understanding_attempts",
              "tutor_sessions",
              "tutor_turns",
              "recurrence_events",
              "ai_call_logs",
              "misconception_observations",
              "adaptive_support_events",
              "evaluation_summary"
            ].map((name) => (
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
        <section className="panel stack">
          <h2>診断履歴</h2>
          {adminError ? <div className="danger">{adminError}</div> : null}
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>被験者</th>
                  <th>用語</th>
                  <th>段階</th>
                  <th>状態</th>
                  <th>主要タイプ</th>
                  <th>信頼度</th>
                  <th>根拠</th>
                  <th>修正</th>
                </tr>
              </thead>
              <tbody>
                {diagnoses.map((row) => {
                  const draft = overrideDrafts[row.observation_id] || {
                    status: row.diagnosed_status,
                    primary: row.primary_misconception_type || "",
                    reason: ""
                  };
                  return (
                    <tr key={row.observation_id}>
                      <td>{row.display_code}</td>
                      <td>{row.term_label}</td>
                      <td>{row.source_phase}</td>
                      <td>{row.diagnosed_status}{row.requires_manual_review ? " / 要確認" : ""}</td>
                      <td>{row.primary_misconception_type || "-"}</td>
                      <td>{row.diagnosis_confidence === null ? "-" : row.diagnosis_confidence.toFixed(2)}</td>
                      <td>{row.diagnosis_evidence || "-"}</td>
                      <td>
                        {row.participant_completed ? (
                          <div className="stack compact">
                            <select
                              value={draft.status}
                              onChange={(event) =>
                                setOverrideDrafts((current) => ({
                                  ...current,
                                  [row.observation_id]: { ...draft, status: event.target.value }
                                }))
                              }
                            >
                              <option value="misconception">misconception</option>
                              <option value="unknown">unknown</option>
                              <option value="ambiguous">ambiguous</option>
                              <option value="resolved">resolved</option>
                            </select>
                            <select
                              value={draft.primary}
                              onChange={(event) =>
                                setOverrideDrafts((current) => ({
                                  ...current,
                                  [row.observation_id]: { ...draft, primary: event.target.value }
                                }))
                              }
                            >
                              <option value="">なし</option>
                              <option value="M1">M1</option>
                              <option value="M2">M2</option>
                              <option value="M3">M3</option>
                              <option value="unknown">unknown</option>
                            </select>
                            <input
                              value={draft.reason}
                              placeholder="修正理由"
                              onChange={(event) =>
                                setOverrideDrafts((current) => ({
                                  ...current,
                                  [row.observation_id]: { ...draft, reason: event.target.value }
                                }))
                              }
                            />
                            <button className="secondary" onClick={() => overrideDiagnosis(row)}>修正</button>
                          </div>
                        ) : "実験完了後に修正可能"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </AppShell>
  );
}

function formatRate(value: number | null) {
  if (value === null || value === undefined) return "-";
  return `${Math.round(value * 100)}%`;
}
