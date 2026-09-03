"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { api } from "@/lib/api";

const GROUP_LABELS: Record<string, string> = {
  proposed: "提案群: ログ適応型AIチューター",
  control: "統制群: 通常AIチューター",
};

export default function ConsentPage() {
  const router = useRouter();
  const [group, setGroup] = useState("proposed");
  const [accepted, setAccepted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const pendingGroup = localStorage.getItem("pending_group_condition");
    if (pendingGroup === "control" || pendingGroup === "proposed") setGroup(pendingGroup);
  }, []);

  async function agreeAndStart() {
    if (!accepted) {
      setError("同意書を確認し、同意してください。");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const data = await api<{ participant_id: string; display_code: string; group_condition: string }>("/api/participants", {
        method: "POST",
        body: JSON.stringify({ group_condition: group, assignment_method: "manual", consent_checked: true }),
      });
      localStorage.setItem("participant_id", data.participant_id);
      localStorage.setItem("display_code", data.display_code);
      localStorage.setItem("group_condition", data.group_condition);
      localStorage.removeItem("pending_group_condition");
      router.push("/pretest");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  }

  return (
    <AppShell step="同意書">
      <section className="panel stack">
        <h1>研究参加同意書（仮）</h1>
        <div className="notice stack">
          <strong>実験の概要</strong>
          <p>専門用語についてテスト、学習セッション、再テストに回答します。</p>
          <strong>保存する情報</strong>
          <p>個人名やメールアドレスは収集せず、回答、回答時間、学習履歴、AI応答を研究用ログとして保存します。</p>
          <strong>参加について</strong>
          <p>参加は任意です。途中で実験を中止できます。保存された研究ログは研究目的で利用します。</p>
        </div>
        <div className="notice">
          <strong>選択された実験条件</strong>
          <p>{GROUP_LABELS[group] || group}</p>
        </div>
        <label className="option">
          <input type="checkbox" checked={accepted} onChange={(event) => setAccepted(event.target.checked)} disabled={submitting} />
          <span>上記を確認し、研究参加と研究用ログの保存に同意します。</span>
        </label>
        {error ? <div className="danger">{error}</div> : null}
        <div className="actions">
          <button className="secondary" type="button" onClick={() => router.push("/start")} disabled={submitting}>
            戻る
          </button>
          <button type="button" onClick={agreeAndStart} disabled={submitting}>
            {submitting ? "開始しています..." : "同意してテストを開始"}
          </button>
        </div>
      </section>
    </AppShell>
  );
}
