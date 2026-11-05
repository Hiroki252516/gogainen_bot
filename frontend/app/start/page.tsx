"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { ParticipantEntryGuard } from "@/components/ParticipantFlowGuard";

export default function StartPage() {
  const router = useRouter();
  const [assignmentCode, setAssignmentCode] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const pendingCode = localStorage.getItem("pending_assignment_code");
    if (pendingCode === "A" || pendingCode === "B") setAssignmentCode(pendingCode);
  }, []);

  function start() {
    const normalizedCode = assignmentCode.trim().toUpperCase();
    if (normalizedCode !== "A" && normalizedCode !== "B") {
      setError("管理者から伝えられた参加コード（AまたはB）を入力してください。");
      return;
    }
    localStorage.setItem("pending_assignment_code", normalizedCode);
    router.push("/consent");
  }

  return (
    <ParticipantEntryGuard>
      <AppShell step="開始">
        <section className="panel stack">
          <h1>専門用語理解の実験を開始します</h1>
          <p className="muted">管理者から伝えられた参加コードを入力し、同意書と事前アンケートへの回答後にテストを開始します。</p>
          <label>
            参加コード
            <input
              value={assignmentCode}
              onChange={(event) => {
                setAssignmentCode(event.target.value.toUpperCase());
                setError("");
              }}
              maxLength={1}
              autoCapitalize="characters"
              autoComplete="off"
              placeholder="A または B"
              aria-describedby={error ? "assignment-code-error" : undefined}
            />
          </label>
          {error ? (
            <div id="assignment-code-error" className="danger" role="alert">
              {error}
            </div>
          ) : null}
          <div className="actions">
            <button onClick={start}>同意書を確認する</button>
          </div>
        </section>
      </AppShell>
    </ParticipantEntryGuard>
  );
}
