"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { ParticipantEntryGuard } from "@/components/ParticipantFlowGuard";
import { postIdempotent } from "@/lib/api";

export default function ConsentPage() {
  const router = useRouter();
  const [assignmentCode, setAssignmentCode] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const pendingCode = localStorage.getItem("pending_assignment_code");
    if (pendingCode === "A" || pendingCode === "B") setAssignmentCode(pendingCode);
  }, []);

  async function agreeAndStart() {
    if (!accepted) {
      setError("同意書を確認し、同意してください。");
      return;
    }
    if (assignmentCode !== "A" && assignmentCode !== "B") {
      setError("開始画面から管理者の参加コードを入力してください。");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const data = await postIdempotent<{ participant_id: string; display_code: string; current_step: string }>(
        "/api/participants",
        { assignment_code: assignmentCode, consent_checked: true },
        "participant:create",
      );
      localStorage.setItem("participant_id", data.participant_id);
      localStorage.setItem("display_code", data.display_code);
      localStorage.removeItem("pending_assignment_code");
      router.replace("/pretest");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  }

  return (
    <ParticipantEntryGuard>
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
            <strong>学習方法の割り当て</strong>
            <p>研究計画に基づき、二つの学習支援方法のいずれかに割り当てられます。参加者が学習方法を選択することはありません。</p>
          </div>
          <label className="option">
            <input type="checkbox" checked={accepted} onChange={(event) => setAccepted(event.target.checked)} disabled={submitting} />
            <span>上記を確認し、研究参加と研究用ログの保存に同意します。</span>
          </label>
          {error ? <div className="danger">{error}</div> : null}
          <div className="actions">
            <button className="secondary" type="button" onClick={() => router.replace("/start")} disabled={submitting}>
              戻る
            </button>
            <button type="button" onClick={agreeAndStart} disabled={submitting}>
              {submitting ? "開始しています..." : "同意してテストを開始"}
            </button>
          </div>
        </section>
      </AppShell>
    </ParticipantEntryGuard>
  );
}
