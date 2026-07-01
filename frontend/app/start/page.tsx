"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { api } from "@/lib/api";

export default function StartPage() {
  const router = useRouter();
  const [group, setGroup] = useState("proposed");
  const [consent, setConsent] = useState(true);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);

  async function start() {
    setError("");
    if (!consent) {
      setError("同意チェックが必要です。");
      return;
    }
    setStarting(true);
    try {
      const data = await api<{ participant_id: string; display_code: string; group_condition: string }>("/api/participants", {
        method: "POST",
        body: JSON.stringify({ group_condition: group, assignment_method: "manual", consent_checked: consent })
      });
      localStorage.setItem("participant_id", data.participant_id);
      localStorage.setItem("display_code", data.display_code);
      localStorage.setItem("group_condition", data.group_condition);
      router.push("/pretest");
    } catch (err) {
      setError(err instanceof Error ? err.message : "実験を開始できませんでした。");
    } finally {
      setStarting(false);
    }
  }

  return (
    <AppShell step="開始">
      <section className="panel stack">
        <h1>専門用語理解の実験を開始します</h1>
        <p className="muted">個人名やメールアドレスは収集しません。選択回答、教材提示、学習進行のログを研究用に保存します。</p>
        <label>
          実験条件
          <select value={group} onChange={(event) => setGroup(event.target.value)}>
            <option value="proposed">提案群: ログ適応型AIチューター</option>
            <option value="control">統制群: 通常AIチューター</option>
          </select>
        </label>
        <label className="option">
          <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} />
          <span>研究用ログ保存に同意します。</span>
        </label>
        {error ? <div className="danger">{error}</div> : null}
        <div className="actions">
          <button onClick={start} disabled={starting}>
            {starting ? "接続中..." : "開始"}
          </button>
        </div>
      </section>
    </AppShell>
  );
}
