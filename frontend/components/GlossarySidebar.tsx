"use client";

import { useEffect, useRef } from "react";
import { LearningGlossary, type Glossary } from "@/components/LearningGlossary";

export function GlossarySidebar({ glossary, label }: { glossary?: Glossary | null; label: string }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const media = window.matchMedia("(min-width: 1100px)");
    const closeOnDesktop = () => {
      if (media.matches && dialogRef.current?.open) dialogRef.current.close();
    };
    media.addEventListener("change", closeOnDesktop);
    return () => media.removeEventListener("change", closeOnDesktop);
  }, []);

  if (!glossary?.entries.length) return null;

  return (
    <>
      <div className="glossary-sidebar">
        <LearningGlossary glossary={glossary} label={label} />
      </div>
      <div className="glossary-mobile">
        <button ref={buttonRef} type="button" className="secondary glossary-open" aria-haspopup="dialog" onClick={() => dialogRef.current?.showModal()}>
          用語の補足
        </button>
        <dialog ref={dialogRef} className="glossary-dialog" aria-label={label} onClose={() => {
          if (buttonRef.current?.getClientRects().length) buttonRef.current.focus();
        }}>
          <button type="button" className="secondary glossary-close" onClick={() => dialogRef.current?.close()} autoFocus>
            閉じる
          </button>
          <LearningGlossary glossary={glossary} label={label} />
        </dialog>
      </div>
    </>
  );
}
