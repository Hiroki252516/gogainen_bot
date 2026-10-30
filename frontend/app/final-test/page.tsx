"use client";

import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { GiveUpButton } from "@/components/GiveUpButton";
import { ParticipantFlowGuard } from "@/components/ParticipantFlowGuard";
import { QuestionRunner } from "@/components/QuestionRunner";

const FINAL_TEST_STEPS = ["final_test"] as const;

export default function FinalTestPage() {
  const [giveUpState, setGiveUpState] = useState({ visible: false, disabled: false });

  return (
    <ParticipantFlowGuard allowedSteps={FINAL_TEST_STEPS}>
      <AppShell
        step="再テスト1"
        headerAction={giveUpState.visible ? <GiveUpButton mode="experiment" disabled={giveUpState.disabled} /> : null}
      >
        <QuestionRunner
          phase="final_test"
          title="再テスト1"
          sourcePath={(id) => `/api/experiment/${id}/final-test`}
          scorePath={(id) => `/api/participants/${id}/score-final-test`}
          nextPath="/survey"
          allowExperimentGiveUp
          onGiveUpStateChange={setGiveUpState}
        />
      </AppShell>
    </ParticipantFlowGuard>
  );
}
