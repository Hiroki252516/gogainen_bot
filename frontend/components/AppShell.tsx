"use client";

import Link from "next/link";

export function AppShell({ step, children }: { step: string; children: React.ReactNode }) {
  return (
    <main className="shell">
      <div className="topbar">
        <div>
          <div className="brand">学習ログ駆動型AIチューター</div>
          <div className="step">{step}</div>
        </div>
        <Link href="/admin">管理画面</Link>
      </div>
      {children}
    </main>
  );
}
