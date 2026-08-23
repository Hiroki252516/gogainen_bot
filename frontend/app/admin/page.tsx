"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { API_BASE, api } from "@/lib/api";

type Participant = { participant_id: string; display_code: string; group_condition: string; current_step: string; completed_at: string | null };
type GroupCondition = "control" | "proposed";

export default function AdminPage() {
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [activeGroup, setActiveGroup] = useState<GroupCondition>("control");
  const [summary, setSummary] = useState<any>(null);
  const [overview, setOverview] = useState<any>(null);
  const [participantLog, setParticipantLog] = useState<any>(null);
  const [ai, setAi] = useState<any>(null);
  const [login, setLogin] = useState<any>(null);
  const [loginError, setLoginError] = useState("");
  const [logError, setLogError] = useState("");
  const [recalculating, setRecalculating] = useState(false);
  const [deletingParticipantId, setDeletingParticipantId] = useState<string | null>(null);

  useEffect(() => {
    api<{ participants: Participant[] }>("/api/admin/participants").then((data) => setParticipants(data.participants));
    api("/api/admin/evaluation-summary").then(setSummary);
    api("/api/admin/logs/overview").then(setOverview);
    api("/api/admin/ai/status").then(setAi);
  }, []);

  useEffect(() => {
    setParticipantLog(null);
    setLogError("");
  }, [activeGroup]);

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

  async function loadParticipantLog(participantId: string) {
    setLogError("");
    try {
      const result = await api(`/api/admin/participants/${participantId}/logs`);
      setParticipantLog(result);
    } catch (err) {
      setLogError(err instanceof Error ? err.message : String(err));
    }
  }

  async function recalculateParticipantSummary(participantId: string) {
    setLogError("");
    setRecalculating(true);
    try {
      await api(`/api/participants/${participantId}/evaluation-summary/recalculate`, { method: "POST" });
      await loadParticipantLog(participantId);
      api("/api/admin/evaluation-summary").then(setSummary);
      api("/api/admin/logs/overview").then(setOverview);
    } catch (err) {
      setLogError(err instanceof Error ? err.message : String(err));
    } finally {
      setRecalculating(false);
    }
  }

  async function deleteParticipant(participant: Participant) {
    const confirmed = window.confirm(`参加者 ${participant.display_code} と関連する実験データを完全に削除します。元に戻せません。続行しますか？`);
    if (!confirmed) return;

    setLogError("");
    setDeletingParticipantId(participant.participant_id);
    try {
      await api(`/api/admin/participants/${participant.participant_id}`, { method: "DELETE" });
      if (participantLog?.participant?.participant_id === participant.participant_id) {
        setParticipantLog(null);
      }
      const [participantData, summaryData, overviewData] = await Promise.all([
        api<{ participants: Participant[] }>("/api/admin/participants"),
        api("/api/admin/evaluation-summary"),
        api("/api/admin/logs/overview")
      ]);
      setParticipants(participantData.participants);
      setSummary(summaryData);
      setOverview(overviewData);
    } catch (err) {
      setLogError(err instanceof Error ? err.message : String(err));
    } finally {
      setDeletingParticipantId(null);
    }
  }

  const activeParticipants = participants.filter((participant) => participant.group_condition === activeGroup);
  const activeGroupSummary = summary?.groups?.find((group: any) => group.group_condition === activeGroup);
  const activeAnswerHistory = (overview?.recent_answer_history || []).filter((row: any) => row.group_condition === activeGroup);
  const activeEvaluationSummaries = (overview?.evaluation_summaries || []).filter((row: any) => row.group_condition === activeGroup);
  const activeAiLogs = (overview?.recent_ai_call_logs || []).filter((row: any) => row.group_condition === activeGroup);

  return (
    <AppShell step="管理画面">
      <div className="stack">
        <section className="panel stack">
          <h1>管理画面</h1>
          <div className="group-tabs" role="tablist" aria-label="実験群">
            {(["control", "proposed"] as GroupCondition[]).map((group) => (
              <button
                key={group}
                className={activeGroup === group ? "group-tab active" : "group-tab"}
                role="tab"
                aria-selected={activeGroup === group}
                onClick={() => setActiveGroup(group)}
              >
                {group}
              </button>
            ))}
          </div>
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
            {activeGroupSummary ? (
              <div className="notice">
                <strong>{activeGroupSummary.group_condition}</strong>
                <p>参加者: {activeGroupSummary.participant_count}</p>
                <p>確認テスト正答率: {formatRate(activeGroupSummary.l0_correct_rate)}</p>
                <p>事前比改善: {formatPoints(activeGroupSummary.avg_score_delta_from_pretest_pt)}</p>
              </div>
            ) : null}
          </div>
          <div className="actions">
            <Link className="button secondary" href="/start">
              実験開始画面へ戻る
            </Link>
            <a className="button secondary" href={`${API_BASE}/api/admin/logs/overview_excel.csv`}>
              全体ログCSV Excel
            </a>
            <a className="button secondary" href={`${API_BASE}/api/admin/logs/overview.csv`}>
              全体ログCSV UTF-8
            </a>
            {participantLog?.participant?.participant_id ? (
              <>
                <a className="button secondary" href={`${API_BASE}/api/admin/participants/${participantLog.participant.participant_id}/logs_excel.csv`}>
                  被験者ログCSV Excel
                </a>
                <a className="button secondary" href={`${API_BASE}/api/admin/participants/${participantLog.participant.participant_id}/logs.csv`}>
                  被験者ログCSV UTF-8
                </a>
              </>
            ) : null}
          </div>
        </section>
        <section className="panel stack">
          <h2>全体ログ</h2>
          <p className="muted">{activeGroup}群の進捗、最近の回答履歴、AI呼び出し、再発イベントを確認します。</p>
          <div className="grid">
            <div className="notice">
              <strong>被験者数</strong>
              <p>{activeParticipants.length}</p>
            </div>
          </div>
          <LogList title="最近の回答履歴" rows={activeAnswerHistory} fields={["display_code", "source_type", "phase", "term_slug", "learning_stage", "component_term", "is_correct", "is_sufficient", "misconception_type", "teaching_strategy", "question_shown_at", "answered_at", "response_time_sec", "created_at"]} />
          <LogList title="評価サマリー" rows={activeEvaluationSummaries} fields={["display_code", "group_condition", "pretest_score", "retest_score", "l0_correct_rate", "same_misconception_recurrence_rate", "completed", "created_at"]} />
          <LogList title="最近のAI呼び出し" rows={activeAiLogs} fields={["purpose", "status", "error_code", "latency_ms", "created_at"]} />
        </section>
        <section className="panel">
          <h2>{activeGroup}群の被験者一覧</h2>
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>条件</th>
                <th>進捗</th>
                <th>完了</th>
                <th>ログ</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {activeParticipants.map((p) => (
                <tr key={p.participant_id}>
                  <td>{p.display_code}</td>
                  <td>{p.group_condition}</td>
                  <td>{p.current_step}</td>
                  <td>{p.completed_at ? "完了" : "未完了"}</td>
                  <td>
                    <button className="secondary" onClick={() => loadParticipantLog(p.participant_id)}>
                      被験者ログを見る
                    </button>
                  </td>
                  <td>
                    <button
                      className="danger-button"
                      disabled={deletingParticipantId === p.participant_id}
                      onClick={() => deleteParticipant(p)}
                    >
                      {deletingParticipantId === p.participant_id ? "削除中..." : "参加者を削除"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section className="panel stack">
          <h2>被験者別ログ</h2>
          {logError ? <p className="danger">{logError}</p> : null}
          {participantLog?.participant ? (
            <>
              <div className="notice">
                <strong>{participantLog.participant.display_code}</strong>
                <p>
                  {participantLog.participant.group_condition} / {participantLog.participant.current_step}
                </p>
                <button className="secondary" disabled={recalculating} onClick={() => recalculateParticipantSummary(participantLog.participant.participant_id)}>
                  {recalculating ? "評価サマリー再計算中..." : "評価サマリーを再計算"}
                </button>
              </div>
              {participantLog.latest_evaluation_summary ? (
                <EvaluationSummary summary={participantLog.latest_evaluation_summary} />
              ) : (
                <section className="insight-panel stack">
                  <div>
                    <h3>評価ログ早見</h3>
                    <p className="muted">まだ評価サマリーがありません。上の「評価サマリーを再計算」を押すと、スコア推移・誤概念推移・学習負担が見えるようになります。</p>
                  </div>
                </section>
              )}
              <ParticipantFlow logs={participantLog} />
              <LogList title="回答履歴（テスト＋学習）" rows={participantLog.answer_history} fields={["source_type", "phase", "term_slug", "learning_stage", "component_term", "is_correct", "is_sufficient", "misconception_type", "teaching_strategy", "question_shown_at", "answered_at", "response_time_sec", "created_at"]} />
              <LogList title="学習状態" rows={participantLog.learner_states} fields={["term_slug", "current_status", "current_stage_for_display", "primary_misconception", "teaching_strategy", "updated_at"]} />
              <SessionLog sessions={participantLog.tutor_sessions || []} />
              <LogList title="AI呼び出しログ" rows={participantLog.ai_call_logs} fields={["purpose", "status", "error_code", "latency_ms", "created_at"]} />
              <LogList title="再発イベント" rows={participantLog.recurrence_events} fields={["term_slug", "previous_misconception_type", "current_misconception_type", "phase", "created_at"]} />
            </>
          ) : (
            <p className="muted">被験者一覧の「被験者ログを見る」を押すと、1人分の流れを確認できます。</p>
          )}
        </section>
      </div>
    </AppShell>
  );
}

function formatRate(value: number | null) {
  if (value === null || value === undefined) return "-";
  return `${Math.round(value * 100)}%`;
}

function formatPoints(value: number | null) {
  if (value === null || value === undefined) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${Math.round(value * 10) / 10}pt`;
}

function EvaluationSummary({ summary }: { summary: any }) {
  const rounds = summary.score_timeline?.rounds || [];
  const burden = summary.learning_burden || {};
  const misconceptionTerms = summary.misconception_timeline?.terms || [];
  const finalRound = rounds.find((round: any) => round.phase === "final_test") || rounds[rounds.length - 1];
  return (
    <section className="insight-panel stack" aria-labelledby="evaluation-insight-title">
      <div className="insight-head">
        <div>
          <h3 id="evaluation-insight-title">評価ログ早見</h3>
          <p className="muted">得点率の推移、誤概念の変化、学習負担をここで確認します。</p>
        </div>
        <div className={`delta-badge ${(finalRound?.score_delta_from_pretest_pt || 0) >= 0 ? "ok" : "bad"}`}>
          事前比 {formatPoints(finalRound?.score_delta_from_pretest_pt)}
        </div>
      </div>
      <div className="flow-summary">
        <Metric label="事前テスト" value={formatRate(summary.pretest_score)} />
        <Metric label="再テスト" value={formatRate(summary.retest_score)} />
        <Metric label="最終テスト" value={formatRate(summary.l0_correct_rate)} />
        <Metric label="再テスト回数" value={`${burden.retest_count ?? 0}回`} />
      </div>
      {rounds.length ? (
        <div className="score-road" aria-label="得点率推移">
          {rounds.map((round: any) => (
            <div className="score-step" key={`${round.round}-${round.attempt_index}`}>
              <div className="score-step-head">
                <strong>{roundLabel(round.round)}</strong>
                <span>{formatRate(round.score_rate)}</span>
              </div>
              <div className="score-bar">
                <span style={{ width: `${Math.max(0, Math.min(100, Number(round.score_rate || 0) * 100))}%` }} />
              </div>
              <div className="score-meta">
                <span>事前比 {formatPoints(round.score_delta_from_pretest_pt)}</span>
                <span>直前比 {formatPoints(round.score_delta_from_previous_test_pt)}</span>
                <span>未達 {round.remaining_learning_target_count ?? "-"}</span>
              </div>
            </div>
          ))}
        </div>
      ) : null}
      <div className="insight-grid">
        <div className="insight-card">
          <h4>誤概念推移</h4>
          {misconceptionTerms.length ? (
            <div className="term-timeline">
              {misconceptionTerms.map((term: any) => (
                <div className="term-row" key={term.term_slug || term.term_label}>
                  <div className="term-row-head">
                    <strong>{term.term_label || term.term_slug}</strong>
                    <span className={`change-pill ${term.change_type || "neutral"}`}>{changeLabel(term.change_type)}</span>
                  </div>
                  <div className="event-chips">
                    {(term.events || []).map((event: any) => (
                      <span className={`event-chip ${event.is_correct ? "ok" : "bad"}`} key={`${event.round}-${event.attempt_index}`}>
                        {roundLabel(event.round)}: {event.is_correct ? "正答" : event.misconception_type || "誤答"}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">誤概念推移はまだありません。</p>
          )}
        </div>
        <div className="insight-card">
          <h4>学習負担</h4>
          <div className="mini-metrics">
            <Metric label="学習セッション" value={`${burden.tutor_session_count ?? 0}回`} />
            <Metric label="学習ターン" value={`${burden.tutor_turn_count ?? 0}回`} />
            <Metric label="学習時間" value={formatSeconds(burden.total_learning_time_sec)} />
            <Metric label="テスト時間" value={formatSeconds(burden.total_test_time_sec)} />
          </div>
        </div>
      </div>
      <details className="raw-json">
        <summary>詳細JSON</summary>
        <pre>{JSON.stringify(summary, null, 2)}</pre>
      </details>
    </section>
  );
}

function roundLabel(round: string) {
  if (!round) return "-";
  if (round === "pretest") return "事前";
  if (round === "final_test") return "最終";
  if (round.startsWith("retest_")) return `再${round.replace("retest_", "")}`;
  return round;
}

function changeLabel(type: string | null | undefined) {
  return (
    {
      resolved: "解消",
      same_type_recurred: "同種再発",
      changed_type: "別タイプ化",
      unknown_persisted: "unknown継続",
      regressed: "後戻り",
      neutral: "変化なし",
    } as Record<string, string>
  )[type || "neutral"] || type || "変化なし";
}

function ParticipantFlow({ logs }: { logs: any }) {
  const rows = [...(logs.answer_history || [])].sort((a: any, b: any) => flowTime(a).localeCompare(flowTime(b)));
  const testRows = rows.filter((row: any) => row.source_type === "test_attempt");
  const learningRows = rows.filter((row: any) => row.source_type === "learning_turn");
  const correctCount = testRows.filter((row: any) => row.is_correct === true).length;
  const incorrectCount = testRows.filter((row: any) => row.is_correct === false).length;
  const sufficientCount = learningRows.filter((row: any) => row.is_sufficient === true).length;
  const insufficientCount = learningRows.filter((row: any) => row.is_sufficient === false).length;
  return (
    <section className="flow-panel stack" aria-labelledby="participant-flow-title">
      <div>
        <h3 id="participant-flow-title">実験フロー</h3>
        <p className="muted">どのフェーズで、どの問題に、何を選び、どう判定されたかを時系列で確認します。</p>
      </div>
      <div className="flow-summary">
        <Metric label="テスト正解" value={`${correctCount}件`} />
        <Metric label="テスト不正解" value={`${incorrectCount}件`} tone={incorrectCount ? "bad" : "ok"} />
        <Metric label="学習十分" value={`${sufficientCount}件`} />
        <Metric label="学習不十分" value={`${insufficientCount}件`} tone={insufficientCount ? "bad" : "ok"} />
      </div>
      <div className="flow-timeline">
        {rows.length ? rows.map((row: any) => <FlowCard key={row.answer_log_id || row.source_id} row={row} />) : <p className="muted">回答ログはまだありません。</p>}
      </div>
    </section>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: "ok" | "bad" }) {
  return (
    <div className={`metric ${tone || ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function FlowCard({ row }: { row: any }) {
  const isTest = row.source_type === "test_attempt";
  const status = isTest ? answerStatus(row.is_correct, "正解", "不正解") : answerStatus(row.is_sufficient, "十分", "不十分");
  return (
    <article className={`flow-card ${status.tone}`}>
      <div className="flow-card-head">
        <div>
          <span className="phase-pill">{phaseLabel(row.phase)}</span>
          <strong>{row.term_label || row.term_slug}</strong>
          {row.component_term ? <span className="muted"> / {row.component_term}</span> : null}
        </div>
        <span className="status-pill">{status.label}</span>
      </div>
      <div className="flow-card-body">
        <div>
          <span className="field-label">問題</span>
          <p>{row.question_body_snapshot || row.question_body || "-"}</p>
        </div>
        <div>
          <span className="field-label">選択した回答</span>
          <p>{row.selected_option_body || row.learner_response || "-"}</p>
        </div>
        <div className="flow-meta">
          <span>誤概念: {row.misconception_type || row.learning_misconception_type || "none"}</span>
          <span>回答時間: {formatSeconds(row.response_time_sec)}</span>
          <span>{formatDateTime(row.answered_at || row.created_at)}</span>
        </div>
      </div>
    </article>
  );
}

function answerStatus(value: boolean | null | undefined, okLabel: string, badLabel: string) {
  if (value === true) return { label: okLabel, tone: "ok" };
  if (value === false) return { label: badLabel, tone: "bad" };
  return { label: "未判定", tone: "neutral" };
}

function phaseLabel(phase: string) {
  const labels: Record<string, string> = {
    pretest: "事前テスト",
    learning: "学習",
    retest: "再テスト",
    final_test: "最終テスト",
    l0_check: "L0確認",
  };
  return labels[phase] || phase || "-";
}

function flowTime(row: any) {
  return row.answered_at || row.created_at || row.question_shown_at || "";
}

function formatSeconds(value: number | null | undefined) {
  if (value === null || value === undefined) return "-";
  return `${Math.round(Number(value) * 10) / 10}秒`;
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return "-";
  return value.replace("T", " ").slice(0, 19);
}

function LogList({ title, rows, fields }: { title: string; rows?: any[]; fields: string[] }) {
  const visibleRows = (rows || []).slice(0, 12);
  return (
    <details className="notice" open={title === "最近のAI呼び出し" ? false : undefined}>
      <summary>{title}</summary>
      {visibleRows.length ? (
        <table className="table compact-table">
          <thead>
            <tr>
              {fields.map((field) => (
                <th key={field}>{field}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row, index) => (
              <tr key={row.id || row.attempt_id || row.tutor_turn_id || index}>
                {fields.map((field) => (
                  <td key={field}>{formatCell(row?.[field])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">ログはまだありません。</p>
      )}
    </details>
  );
}

function SessionLog({ sessions }: { sessions: any[] }) {
  return (
    <details className="notice">
      <summary>学習セッション</summary>
      {sessions.length ? (
        <div className="stack">
          {sessions.map((session) => (
            <div className="notice" key={session.tutor_session_id}>
              <strong>
                {session.term_label} session {session.session_index}
              </strong>
              <LogList title="学習ターン詳細" rows={session.turns} fields={["turn_index", "learning_stage", "component_term", "next_learning_stage", "is_sufficient", "learning_misconception_type", "teaching_strategy", "question_shown_at", "answered_at", "response_time_sec", "created_at"]} />
              {session.turns?.slice(0, 3).map((turn: any) => (
                <details key={turn.tutor_turn_id}>
                  <summary>turn {turn.turn_index} 詳細</summary>
                  <pre>{JSON.stringify(turn, null, 2)}</pre>
                </details>
              ))}
            </div>
          ))}
        </div>
      ) : (
        <p className="muted">学習セッションはまだありません。</p>
      )}
    </details>
  );
}

function formatCell(value: any) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
