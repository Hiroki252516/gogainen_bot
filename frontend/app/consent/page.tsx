"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { ParticipantEntryGuard } from "@/components/ParticipantFlowGuard";
import { api, ApiError } from "@/lib/api";
import { ConsentDocument } from "@/components/ConsentDocument";

export default function ConsentPage() {
  const router = useRouter();
  const [assignmentCode, setAssignmentCode] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [studentNumber, setStudentNumber] = useState("");
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
    if (!/^[0-9]{1,64}$/.test(studentNumber)) {
      setError("学籍番号は半角数字1〜64桁で入力してください。");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      // Persist only an opaque retry key. Never persist the body containing the student number.
      let key = sessionStorage.getItem("registration_request_key");
      if (!key) {
        key = crypto.randomUUID();
        sessionStorage.setItem("registration_request_key", key);
      }
      const data = await api<{ participant_id: string; display_code: string; current_step: string }>(
        "/api/registrations", {
          method: "POST", headers: { "Idempotency-Key": key }, timeoutMs: 15000,
          body: JSON.stringify({ assignment_code: assignmentCode, consent_checked: true, student_number: studentNumber }),
        });
      setStudentNumber("");
      sessionStorage.removeItem("registration_request_key");
      localStorage.setItem("participant_id", data.participant_id);
      localStorage.setItem("display_code", data.display_code);
      localStorage.removeItem("pending_assignment_code");
      router.replace("/presurvey");
    } catch (err) {
      if (err instanceof ApiError && err.status >= 400 && err.status < 500 && !err.code?.startsWith("idempotency_")) {
        sessionStorage.removeItem("registration_request_key");
      }
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  }

  return (
    <ParticipantEntryGuard>
      <AppShell step="同意書">
        <section className="panel stack">
          <h1>研究参加同意書</h1>
          <p className="danger" role="status">未確定項目を含む動作確認用です。責任者・保存場所・保管期間および管理アクセス対策の確定前に、本実験のデータを収集しないでください。</p>
          <ConsentDocument />
          <label>学籍番号（必須）
            <input value={studentNumber}
              onChange={(event) => setStudentNumber(event.target.value.replace(/[^0-9]/g, ""))}
              required maxLength={64} inputMode="numeric" pattern="[0-9]*"
              autoComplete="off" autoCapitalize="none" spellCheck={false} disabled={submitting} />
          </label>
          <p className="muted">学籍番号は撤回時の対応表にのみ使用し、研究用データやAIへの入力には含めません。</p>
          <h2>同意確認</h2>
          <label className="option">
            <input type="checkbox" checked={accepted} onChange={(event) => setAccepted(event.target.checked)} disabled={submitting} />
            <span>説明を読み、その内容を理解した上で、本実験に参加することに同意します。</span>
          </label>
          {error ? <div className="danger" role="alert">{error}</div> : null}
          <div className="actions">
            <button className="secondary" type="button" onClick={() => router.replace("/start")} disabled={submitting}>
              戻る
            </button>
            <button type="button" onClick={agreeAndStart} disabled={submitting}>
              {submitting ? "開始しています..." : "同意して事前アンケートへ"}
            </button>
          </div>
        </section>
      </AppShell>
    </ParticipantEntryGuard>
  );
}
