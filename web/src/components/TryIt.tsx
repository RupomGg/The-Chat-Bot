"use client";
import Script from "next/script";
import { WIDGET_ORIGIN } from "@/content/site";

// Loads the real chat widget and opens it. Renders nothing until the backend is live.
export function TryIt({ withScript = false }: { withScript?: boolean }) {
  if (!WIDGET_ORIGIN) return null;
  const open = () =>
    (document.querySelector("chat-widget")?.shadowRoot?.querySelector(".launch") as HTMLElement | null)?.click();
  return (
    <>
      {withScript && <Script src={`${WIDGET_ORIGIN}/widget.js`} data-company="demo" strategy="lazyOnload" />}
      <button type="button" onClick={open}
        className="inline-flex min-h-12 items-center rounded-full bg-surface px-6 font-semibold ring-1 ring-line ring-inset active:translate-y-px">
        Try it
      </button>
    </>
  );
}
