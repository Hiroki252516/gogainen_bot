"use client";

import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ParticipantFlowGuard } from "@/components/ParticipantFlowGuard";
import { QuestionRunner } from "@/components/QuestionRunner";

const retestSourcePath = (id: string) => `/api/experiment/${id}/retest`;
const retestScorePath = (id: string) => `/api/participants/${id}/score-retest`;
const RETEST_STEPS = ["retest"] as const;

export default function RetestPage() {
  const [roundTitle, setRoundTitle] = useState("再テスト1");

  return (
    <ParticipantFlowGuard allowedSteps={RETEST_STEPS}>
      <AppShell step={roundTitle}>
        <QuestionRunner
          phase="retest"
          title="再テスト1"
          sourcePath={retestSourcePath}
          scorePath={retestScorePath}
          nextPath="/learning-targets"
          onDisplayTitle={setRoundTitle}
          allowExperimentGiveUp
        />
      </AppShell>
    </ParticipantFlowGuard>
  );
}
