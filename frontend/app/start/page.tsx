"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";

export default function StartPage() {
  const router = useRouter();
  const [group, setGroup] = useState("proposed");

  function start() {
    localStorage.setItem("pending_group_condition", group);
    router.push("/consent");
  }

  return (
    <AppShell step="開始">
      <section className="panel stack">
        <h1>専門用語理解の実験を開始します</h1>
        <p className="muted">実験条件を選択し、同意書を確認してからテストを開始します。</p>
        <label>
          実験条件
          <select value={group} onChange={(event) => setGroup(event.target.value)}>
            <option value="proposed">提案群: ログ適応型AIチューター</option>
            <option value="control">統制群: 通常AIチューター</option>
          </select>
        </label>
        <div className="actions">
          <button onClick={start}>実験を開始する</button>
        </div>
      </section>
    </AppShell>
  );
}
