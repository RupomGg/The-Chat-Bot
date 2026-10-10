"use client";
import { useEffect, useState } from "react";
import { chats, type Chat } from "@/content/site";

// Steps: 0 time, 1 customer, 2 typing, 3 reply, 4 chips, 5 pick, 6 booked.
const WAITS = [200, 500, 900, 1300, 700, 1300, 900];

function Thread({ chat, step }: { chat: Chat; step: number }) {
  return (
    <div lang={chat.lang} className="flex min-h-[400px] flex-col gap-2 px-1 pt-4 pb-1 text-[15px] leading-normal">
      {step >= 0 && <div className="pop self-center text-xs text-soft">11:42 pm</div>}
      {step >= 1 && <div className="pop max-w-[84%] self-end rounded-2xl rounded-br-sm bg-brand px-3.5 py-2 text-on-brand">{chat.c1}</div>}
      {step === 2 && (
        <div className="flex gap-1 self-start rounded-2xl bg-wash px-3.5 py-3">
          {[0, 1, 2].map((i) => <i key={i} className="blink size-1.5 rounded-full bg-soft" style={{ animationDelay: `${i * 0.15}s` }} />)}
        </div>
      )}
      {step >= 3 && <div className="pop max-w-[84%] self-start rounded-2xl rounded-bl-sm bg-wash px-3.5 py-2">{chat.b1}</div>}
      {step >= 4 && (
        <div className="pop flex flex-wrap gap-1.5">
          {chat.chips.map((c, i) => (
            <span key={c} className={`rounded-full px-3 py-1 text-sm font-medium ring-1 ring-brand ring-inset ${step >= 5 && i === chat.pick ? "bg-brand text-on-brand" : "text-brand"}`}>{c}</span>
          ))}
        </div>
      )}
      {step >= 5 && <div className="pop max-w-[84%] self-end rounded-2xl rounded-br-sm bg-brand px-3.5 py-2 text-on-brand">{chat.chips[chat.pick]}</div>}
      {step >= 6 && (
        <div className="pop max-w-[84%] self-start rounded-2xl rounded-bl-sm bg-wash px-3.5 py-2">
          {chat.done} <span className="ml-1 rounded-full bg-sun px-2 py-px text-xs font-semibold text-[#1a1b21]">Booked</span>
        </div>
      )}
    </div>
  );
}

export function Phone({ chat, step = 6 }: { chat: Chat; step?: number }) {
  return (
    <div aria-label="Example conversation" className="w-full max-w-[380px] rounded-[28px] border border-line bg-surface p-3.5 shadow-[0_1px_2px_rgb(22_24_29/.04),0_16px_40px_rgb(36_83_214/.12)]">
      <div className="flex items-center gap-2.5 border-b border-line px-1.5 pb-3">
        <div className="grid size-9 place-items-center rounded-full bg-wash font-display font-bold text-brand">{chat.biz[0]}</div>
        <div className="leading-tight">
          <b className="block text-[15px] font-semibold">{chat.biz}</b>
          <small className="text-[13px] text-soft">Replies instantly · Example</small>
        </div>
      </div>
      <Thread chat={chat} step={step} />
    </div>
  );
}

// Hero: plays every industry in turn; dots pick one. Reduced motion shows the finished chat.
export function ChatMockup() {
  const [n, setN] = useState(0);
  const [step, setStep] = useState(-1);

  const show = (i: number) => { setStep(-1); setN(i); };

  useEffect(() => {
    let t: ReturnType<typeof setTimeout>;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
      t = setTimeout(() => setStep(6), 0);
      return () => clearTimeout(t);
    }
    let s = -1;
    const next = () => {
      if (s < 6) { s += 1; setStep(s); t = setTimeout(next, WAITS[s + 1] ?? 0); }
      else t = setTimeout(() => !document.hidden && show((n + 1) % chats.length), 4000);
    };
    t = setTimeout(next, WAITS[0]);
    return () => clearTimeout(t);
  }, [n]);

  return (
    <div className="flex flex-col items-center gap-4">
      <Phone chat={chats[n]} step={step} />
      <div className="flex gap-1.5" role="group" aria-label="Example conversations">
        {chats.map((c, i) => (
          <button key={c.tab} type="button" aria-label={c.tab} aria-pressed={i === n} onClick={() => show(i)}
            className={`h-2 rounded-full transition-all ${i === n ? "w-6 bg-brand" : "w-2 bg-line"}`} />
        ))}
      </div>
    </div>
  );
}
