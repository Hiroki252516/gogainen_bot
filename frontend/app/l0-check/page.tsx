"use client";

import { AppShell } from "@/components/AppShell";
import { ParticipantFlowGuard } from "@/components/ParticipantFlowGuard";
import { QuestionRunner } from "@/components/QuestionRunner";

const L0_CHECK_STEPS = ["l0_check", "final_test"] as const;

export default function ConfirmationCheckPage() {
  return (
    <ParticipantFlowGuard allowedSteps={L0_CHECK_STEPS}>
      <AppShell step="確認テスト">
        <QuestionRunner
          phase="l0_check"
          title="確認テスト"
          sourcePath={(id) => `/api/experiment/${id}/l0-check`}
          scorePath={(id) => `/api/participants/${id}/score-l0-check`}
          nextPath="/finish"
        />
      </AppShell>
    </ParticipantFlowGuard>
  );
}
