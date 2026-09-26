"use client";

import type { ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, api, clearParticipantSession, participantId } from "@/lib/api";

type CurrentStepResponse = {
  step: string;
  next_url: string;
};

type LearningTargetsResponse = {
  targets: Array<{ term_slug: string }>;
};

export function CheckingFlow({ error = false, onRetry }: { error?: boolean; onRetry?: () => void } = {}) {
  return (
    <section className="panel" aria-busy="true" role="status">
      {error ? (
        <>
          <p>実験の現在位置を確認できませんでした。</p>
          {onRetry ? <button type="button" onClick={onRetry}>もう一度確認</button> : null}
        </>
      ) : (
        "実験の現在位置を確認しています..."
      )}
    </section>
  );
}

export function useParticipantFlowGuard(allowedSteps: readonly string[]) {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(false);
  const [checkError, setCheckError] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let active = true;
    setReady(false);
    setCheckError(false);
    const id = participantId();
    if (!id) {
      router.replace("/start");
      return () => {
        active = false;
      };
    }

    api<CurrentStepResponse>(`/api/participants/${id}/current-step`)
      .then((data) => {
        if (!active) return;
        if (allowedSteps.includes(data.step)) {
          setReady(true);
          return;
        }
        const nextUrl = data.next_url || "/start";
        if (nextUrl === pathname) {
          setReady(true);
        } else {
          router.replace(nextUrl);
        }
      })
      .catch((error) => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 404) {
          clearParticipantSession();
          router.replace("/start");
          return;
        }
        // Do not expose a stale page after a failed status check.
        setCheckError(true);
      });

    return () => {
      active = false;
    };
  }, [allowedSteps, pathname, retryCount, router]);

  return { ready, error: checkError, retry: () => setRetryCount((count) => count + 1) };
}

export function useLearningTargetFlowGuard(termSlug: string) {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(false);
  const [checkError, setCheckError] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let active = true;
    setReady(false);
    setCheckError(false);
    const id = participantId();
    if (!id) {
      router.replace("/start");
      return () => {
        active = false;
      };
    }

    async function check() {
      try {
        const step = await api<CurrentStepResponse>(`/api/participants/${id}/current-step`);
        if (!active) return;
        if (step.step !== "learning_targets") {
          const nextUrl = step.next_url || "/start";
          if (nextUrl === pathname) setReady(true);
          else router.replace(nextUrl);
          return;
        }

        const data = await api<LearningTargetsResponse>(`/api/participants/${id}/learning-targets`);
        if (!active) return;
        const targetSlugs = data.targets.map((target) => target.term_slug);
        if (targetSlugs.includes(termSlug)) {
          setReady(true);
        } else {
          router.replace("/learning-targets");
        }
      } catch (error) {
        if (!active) return;
        if (error instanceof ApiError && error.status === 404) {
          clearParticipantSession();
          router.replace("/start");
          return;
        }
        // Do not expose a stale learning page after a failed status check.
        setCheckError(true);
      }
    }

    check();
    return () => {
      active = false;
    };
  }, [pathname, retryCount, router, termSlug]);

  return { ready, error: checkError, retry: () => setRetryCount((count) => count + 1) };
}

export function ParticipantFlowGuard({
  allowedSteps,
  children,
}: {
  allowedSteps: readonly string[];
  children: ReactNode;
}) {
  const flow = useParticipantFlowGuard(allowedSteps);
  return flow.ready ? <>{children}</> : <CheckingFlow error={flow.error} onRetry={flow.retry} />;
}

export function ParticipantEntryGuard({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(false);
  const [checkError, setCheckError] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let active = true;
    setReady(false);
    setCheckError(false);
    const id = participantId();
    if (!id) {
      setReady(true);
      return () => {
        active = false;
      };
    }

    api<CurrentStepResponse>(`/api/participants/${id}/current-step`)
      .then((data) => {
        if (!active) return;
        const nextUrl = data.next_url || "/start";
        if (nextUrl === pathname) {
          setReady(true);
        } else {
          router.replace(nextUrl);
        }
      })
      .catch((error) => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 404) {
          clearParticipantSession();
          setReady(true);
          return;
        }
        // Do not expose the entry form when an existing participant cannot be checked.
        setCheckError(true);
      });

    return () => {
      active = false;
    };
  }, [pathname, retryCount, router]);

  return ready ? <>{children}</> : <CheckingFlow error={checkError} onRetry={() => setRetryCount((count) => count + 1)} />;
}
