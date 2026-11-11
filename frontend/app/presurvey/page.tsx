"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { ParticipantFlowGuard } from "@/components/ParticipantFlowGuard";
import { PresurveyQuestionnaire, type PresurveySubmission, type SurveyTermItem } from "@/components/SurveyForms";
import { api, postIdempotent, requireParticipant } from "@/lib/api";

const PRESURVEY_STEPS = ["presurvey"] as const;
type Context = { survey_version: string; term_items: SurveyTermItem[] };

export default function PresurveyPage() {
  const router = useRouter();
  const [context, setContext] = useState<Context | null>(null);
  const [error, setError] = useState("");

  async function loadContext() {
    setError("");
    try { setContext(await api<Context>(`/api/participants/${requireParticipant()}/presurvey`)); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }

  useEffect(() => { void loadContext(); }, []);

  async function submit(payload: PresurveySubmission) {
    const participantId = requireParticipant();
    await postIdempotent(`/api/participants/${participantId}/presurvey`, payload, `presurvey:${participantId}`);
    router.replace("/pretest");
  }

  return <ParticipantFlowGuard allowedSteps={PRESURVEY_STEPS}>
    <AppShell step="事前アンケート">
      {context ? <PresurveyQuestionnaire
        surveyVersion={context.survey_version}
        termItems={context.term_items}
        onSubmit={submit}
      /> : <section className="panel stack">
        <h1>実験前アンケート</h1>
        <p>回答項目を確認しています。</p>
        {error ? <div className="danger" role="alert">{error}</div> : null}
        {error ? <button type="button" onClick={() => void loadContext()}>再読み込み</button> : null}
      </section>}
    </AppShell>
  </ParticipantFlowGuard>;
}
