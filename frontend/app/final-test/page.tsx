"use client";

import { AppShell } from "@/components/AppShell";
import { ParticipantFlowGuard } from "@/components/ParticipantFlowGuard";
import { QuestionRunner } from "@/components/QuestionRunner";

const FINAL_TEST_STEPS = ["final_test"] as const;

export default function FinalTestPage() {
  return (
    <ParticipantFlowGuard allowedSteps={FINAL_TEST_STEPS}>
      <AppShell step="再テスト1">
        <QuestionRunner
          phase="final_test"
          title="再テスト1"
          sourcePath={(id) => `/api/experiment/${id}/final-test`}
          scorePath={(id) => `/api/participants/${id}/score-final-test`}
          nextPath="/survey"
          allowExperimentGiveUp
        />
      </AppShell>
    </ParticipantFlowGuard>
  );
}
