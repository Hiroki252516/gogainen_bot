"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { api, requireParticipant } from "@/lib/api";

export default function PreSurveyPage() {
  const router = useRouter();
  const [saving, setSaving] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    const form = new FormData(event.currentTarget);
    const body = {
      phase: "pre_survey",
      ai_experience_level: Number(form.get("ai")),
      programming_experience_level: Number(form.get("programming")),
      llm_usage_level: Number(form.get("llm")),
      self_rated_ai_knowledge: Number(form.get("knowledge")),
      term_confidences: {
        attention: Number(form.get("attention")),
        embedding: Number(form.get("embedding")),
        rag: Number(form.get("rag"))
      }
    };
    await api(`/api/participants/${requireParticipant()}/survey`, { method: "POST", body: JSON.stringify(body) });
    router.push("/pretest");
  }

  return (
    <AppShell step="事前アンケート">
      <form className="panel stack" onSubmit={submit}>
        <h1>事前アンケート</h1>
        <div className="grid">
          {[
            ["ai", "AI・機械学習の学習経験"],
            ["programming", "プログラミング経験"],
            ["llm", "ChatGPT等の利用経験"],
            ["knowledge", "AI用語への自信"]
          ].map(([name, label]) => (
            <label key={name}>
              {label}
              <select name={name} defaultValue="3">
                {[1, 2, 3, 4, 5].map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
        <h2>用語別自信度</h2>
        <div className="grid">
          {["attention", "embedding", "rag"].map((name) => (
            <label key={name}>
              {name}
              <select name={name} defaultValue="3">
                {[1, 2, 3, 4, 5].map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
        <button disabled={saving}>事前テストへ</button>
      </form>
    </AppShell>
  );
}
