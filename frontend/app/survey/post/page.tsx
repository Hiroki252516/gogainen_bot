"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { api, requireParticipant } from "@/lib/api";

export default function PostSurveyPage() {
  const router = useRouter();
  const [saving, setSaving] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    const form = new FormData(event.currentTarget);
    const id = requireParticipant();
    await api(`/api/participants/${id}/survey`, {
      method: "POST",
      body: JSON.stringify({
        phase: "post_survey",
        usability_rating: Number(form.get("usability")),
        helpfulness_rating: Number(form.get("helpfulness")),
        perceived_hint_amount: Number(form.get("hint")),
        free_comment: String(form.get("comment") || "")
      })
    });
    await api(`/api/participants/${id}/evaluation-summary/recalculate`, { method: "POST" });
    router.push("/finish");
  }

  return (
    <AppShell step="事後アンケート">
      <form className="panel stack" onSubmit={submit}>
        <h1>事後アンケート</h1>
        <div className="grid">
          {[
            ["usability", "使いやすさ"],
            ["helpfulness", "分かりやすさ"],
            ["hint", "ヒント量の適切さ"]
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
        <label>
          自由記述
          <textarea name="comment" />
        </label>
        <button disabled={saving}>終了</button>
      </form>
    </AppShell>
  );
}
