"use client";

import { AppShell } from "@/components/AppShell";
import { ParticipantFlowGuard } from "@/components/ParticipantFlowGuard";
import { QuestionRunner } from "@/components/QuestionRunner";

const PRETEST_STEPS = ["pretest"] as const;

export default function PretestPage() {
  return (
    <ParticipantFlowGuard allowedSteps={PRETEST_STEPS}>
      <AppShell step="テスト">
        <QuestionRunner phase="pretest" title="テスト" sourcePath={(id) => `/api/experiment/${id}/pretest`} nextPath="/diagnosing" />
      </AppShell>
    </ParticipantFlowGuard>
  );
}
