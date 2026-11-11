"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { ParticipantFlowGuard } from "@/components/ParticipantFlowGuard";
import { PosttestQuestionnaire, type PosttestSubmission } from "@/components/SurveyForms";
import { api, postIdempotent, requireParticipant } from "@/lib/api";

const SURVEY_STEPS = ["survey"] as const;
type Context = { survey_version: "posttest-5point-v1"; material_ratings_required: boolean };

export default function SurveyPage() {
  const router = useRouter();
  const [context, setContext] = useState<Context | null>(null);
  const [error, setError] = useState("");

  async function loadContext() {
    setError("");
    try { setContext(await api<Context>(`/api/participants/${requireParticipant()}/survey`)); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }

  useEffect(() => { void loadContext(); }, []);

  async function submit(payload: PosttestSubmission) {
    const participantId = requireParticipant();
    await postIdempotent(`/api/participants/${participantId}/survey`, payload, `survey:${participantId}`);
    router.replace("/finish");
  }

  return <ParticipantFlowGuard allowedSteps={SURVEY_STEPS}>
    <AppShell step="アンケート">
      {context ? <PosttestQuestionnaire materialRatingsRequired={context.material_ratings_required} onSubmit={submit} /> : <section className="panel stack">
        <h1>実験後アンケート</h1>
        <p>回答項目を確認しています。</p>
        {error ? <div className="danger" role="alert">{error}</div> : null}
        {error ? <button type="button" onClick={() => void loadContext()}>再読み込み</button> : null}
      </section>}
    </AppShell>
  </ParticipantFlowGuard>;
}
