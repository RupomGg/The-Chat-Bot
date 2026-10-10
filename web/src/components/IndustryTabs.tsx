"use client";
import { useRef, useState } from "react";
import { GraduationCap, PawPrint, Stethoscope, Scales } from "@phosphor-icons/react";
import { chats } from "@/content/site";
import { Phone } from "./ChatMockup";

const ICONS = [GraduationCap, PawPrint, Stethoscope, Scales];

export function IndustryTabs() {
  const [n, setN] = useState(0);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const c = chats[n];
  const go = (i: number) => { setN(i); tabs.current[i]?.focus(); };

  return (
    <>
      <div role="tablist" aria-label="Industries" className="mt-9 mb-8 flex gap-2 overflow-x-auto pb-1">
        {chats.map((ch, i) => {
          const Icon = ICONS[i];
          return (
            <button key={ch.tab} ref={(el) => { tabs.current[i] = el; }} role="tab" type="button"
              id={`tab-${i}`} aria-selected={i === n} tabIndex={i === n ? 0 : -1} onClick={() => setN(i)}
              onKeyDown={(e) => {
                if (e.key === "ArrowRight") go((i + 1) % chats.length);
                if (e.key === "ArrowLeft") go((i + chats.length - 1) % chats.length);
              }}
              className={`inline-flex min-h-11 shrink-0 items-center gap-2 rounded-full px-5 font-medium transition-colors ${i === n ? "bg-brand text-on-brand" : "bg-surface ring-1 ring-line ring-inset hover:text-brand"}`}>
              <Icon size={20} aria-hidden /> {ch.tab}
            </button>
          );
        })}
      </div>
      <div role="tabpanel" aria-labelledby={`tab-${n}`} className="grid items-start gap-10 lg:grid-cols-[1fr_380px]">
        <div className="grid gap-7">
          <div>
            <h3 className="mb-3 font-display text-xl font-semibold">They ask</h3>
            <div className="flex flex-wrap gap-2">
              {c.asks.map((q) => <span key={q} className="rounded-2xl bg-surface px-3 py-1.5 ring-1 ring-line ring-inset">{q}</span>)}
            </div>
          </div>
          <div>
            <h3 className="mb-2 font-display text-xl font-semibold">Halcyo does</h3>
            <p className="max-w-[60ch] text-soft">{c.does}</p>
          </div>
          <div className="rounded-2xl bg-wash-sun px-5 py-4">
            <h3 className="mb-1 font-display text-xl font-semibold">Never does</h3>
            <p className="max-w-[60ch]">{c.never}</p>
          </div>
        </div>
        <Phone chat={c} />
      </div>
    </>
  );
}
