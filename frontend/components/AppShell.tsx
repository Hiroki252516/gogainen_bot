"use client";

import Link from "next/link";
import type { MouseEvent, ReactNode } from "react";
import { ExperimentProgress } from "@/components/ExperimentProgress";

const ADMIN_NAVIGATION_CONFIRM_MESSAGE =
  "管理画面を開きます。現在の実験画面から移動しますが、実験データは削除されません。よろしいですか？";

function confirmAdminNavigation(event: MouseEvent<HTMLAnchorElement>) {
  if (!window.confirm(ADMIN_NAVIGATION_CONFIRM_MESSAGE)) {
    event.preventDefault();
  }
}

export function AppShell({ step, children, headerAction }: { step: string; children: ReactNode; headerAction?: ReactNode }) {
  const isAdminPage = step === "管理画面";

  return (
    <main className="shell">
      <div className="topbar app-topbar">
        <div>
          <div className="brand">学習ログ駆動型AIチューター</div>
          <div className="step">{step}</div>
        </div>
        <div className="app-header-actions">
          {!isAdminPage && headerAction ? <div className="app-header-give-up">{headerAction}</div> : null}
          <Link href="/admin" onClick={isAdminPage ? undefined : confirmAdminNavigation}>
            管理画面
          </Link>
        </div>
      </div>
      {!isAdminPage ? <ExperimentProgress /> : null}
      {children}
    </main>
  );
}
