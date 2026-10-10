import Image from "next/image";
import {
  ArrowRight, ArrowUpRight, Check, Hourglass, MoonStars, Plus, Receipt, ShieldCheck, Translate, Tray, RocketLaunch, WhatsappLogo,
} from "@phosphor-icons/react/ssr";
import { BOOK, HERO_IMAGE, faqs, plans, problems, steps, wa } from "@/content/site";
import { ChatMockup } from "@/components/ChatMockup";
import { IndustryTabs } from "@/components/IndustryTabs";
import { TryIt } from "@/components/TryIt";
import { ThemeToggle } from "@/components/ThemeToggle";
import founder from "@/images/founder.webp";

const btn = "inline-flex min-h-12 items-center justify-center gap-2 rounded-full px-6 font-semibold whitespace-nowrap transition active:translate-y-px";
const primary = `${btn} bg-brand text-on-brand hover:brightness-95`;
const wrap = "mx-auto max-w-6xl px-5 md:px-8";
const h2 = "font-display text-3xl font-semibold leading-tight sm:text-4xl";
const PROBLEM_ICONS = { hourglass: Hourglass, moon: MoonStars, receipt: Receipt };

// Slow drifting light + rising speech bubbles. CSS only; off under reduced motion.
function AnimatedBackground() {
  const bubbles = [[4, 22, 0], [15, 34, -9], [27, 18, -21], [41, 28, -4], [55, 40, -15], [66, 24, -27], [78, 32, -2], [90, 20, -18]];
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
      <div className="glow-a absolute -top-40 -right-32 size-[560px] rounded-full bg-brand/15 blur-3xl" />
      <div className="glow-b absolute -bottom-56 -left-40 size-[560px] rounded-full bg-sun/20 blur-3xl" />
      {bubbles.map(([left, size, delay], i) => (
        <svg key={i} className="rise absolute -bottom-20 text-brand/20" width={size + 14} height={size + 14} viewBox="0 0 32 32"
          fill="none" stroke="currentColor" strokeWidth="1.5"
          style={{ left: `${left}%`, animationDuration: `${24 + (i % 4) * 5}s`, animationDelay: `${delay}s` }}>
          <path d="M6 5h20a3 3 0 0 1 3 3v12a3 3 0 0 1-3 3H14l-6 5v-5H6a3 3 0 0 1-3-3V8a3 3 0 0 1 3-3z" />
        </svg>
      ))}
    </div>
  );
}

export default function Home() {
  return (
    <>
      <header className="sticky top-0 z-50 border-b border-line bg-bg/90 backdrop-blur-md">
        <nav aria-label="Main" className={`${wrap} flex h-16 items-center gap-8`}>
          <a href="#top" className="flex items-center gap-2 font-display text-2xl font-bold">
            <span className="grid size-8 place-items-center rounded-full bg-brand text-sm text-on-brand">h</span>halcyo
          </a>
          <div className="hidden gap-7 text-[15px] font-medium text-soft md:flex">
            <a href="#how" className="hover:text-brand">How it works</a>
            <a href="#industries" className="hover:text-brand">Industries</a>
            <a href="#pricing" className="hover:text-brand">Pricing</a>
            <a href="#faq" className="hover:text-brand">FAQ</a>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <ThemeToggle />
            <a href={BOOK} target="_blank" rel="noopener" className={`${primary} min-h-10 px-5 text-sm`}>Book a demo</a>
          </div>
        </nav>
      </header>

      <main id="top">
        {/* Hero */}
        <section className="relative isolate overflow-hidden pt-12 pb-20 md:pt-20 md:pb-28">
          <AnimatedBackground />
          <div className={`${wrap} grid items-center gap-14 lg:grid-cols-2`}>
            <div className="flex flex-col gap-6">
              <h1 className="font-display text-[40px] leading-[1.1] font-bold sm:text-5xl lg:text-[56px]">
                Every customer message answered. <span className="block text-brand">Even at 11 pm.</span>
              </h1>
              <p className="max-w-xl text-lg leading-relaxed text-soft">
                Halcyo replies on Messenger, WhatsApp and your website in Bangla, Banglish or English, and books appointments for you while your team rests.
              </p>
              <div className="flex flex-wrap gap-3">
                <a href={BOOK} target="_blank" rel="noopener" className={primary}><WhatsappLogo size={20} aria-hidden />Book a demo</a>
                <TryIt withScript />
              </div>
            </div>
            <div className="relative flex flex-col items-center">
              <div className="relative w-full overflow-hidden rounded-3xl border border-line">
                <Image src={HERO_IMAGE} alt="A staff member at a Dhaka office smiling while replying to customer messages"
                  width={1200} height={800} priority sizes="(min-width: 1024px) 560px, 100vw" className="h-72 w-full object-cover sm:h-80" />
              </div>
              <div className="relative z-10 -mt-16 w-[92%] sm:w-[84%]"><ChatMockup /></div>
            </div>
          </div>
        </section>

        {/* Problem */}
        <section className="border-y border-line bg-sand py-16">
          <div className={wrap}>
            <h2 className={`${h2} mb-10 max-w-2xl`}>Why service businesses lose warm customers.</h2>
            <div className="grid gap-6 md:grid-cols-3">
              {problems.map((p) => {
                const Icon = PROBLEM_ICONS[p.icon as keyof typeof PROBLEM_ICONS];
                return (
                  <div key={p.title} className="rounded-2xl border border-line bg-surface p-6">
                    <Icon size={30} className="text-brand" aria-hidden />
                    <h3 className="mt-3 font-display text-lg font-semibold">{p.title}</h3>
                    <p className="mt-2 text-[15px] leading-relaxed text-soft">{p.text}</p>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        {/* Industries */}
        <section id="industries" className="py-20">
          <div className={wrap}>
            <h2 className={`${h2} max-w-2xl`}>Made for businesses that sell time, care or advice.</h2>
            <p className="mt-3 max-w-2xl text-soft">Every business has professional boundaries. Halcyo is told exactly what it does, and what it must never do.</p>
            <IndustryTabs />
            <p className="mt-10 text-soft">
              Different business? If you sell a service and take bookings, it probably fits.{" "}
              <a href={BOOK} target="_blank" rel="noopener" className="font-semibold text-brand underline underline-offset-4">Ask us.</a>
            </p>
          </div>
        </section>

        {/* How it works */}
        <section id="how" className="border-y border-line bg-sand py-20">
          <div className={`${wrap} grid gap-12 lg:grid-cols-12`}>
            <div className="self-start lg:sticky lg:top-28 lg:col-span-5">
              <h2 className={h2}>From a message at night to a booking by morning.</h2>
              <p className="mt-4 text-soft">You see every conversation in one inbox. Reply any time, and the bot steps back.</p>
            </div>
            <ol className="grid gap-3 lg:col-span-7">
              {steps.map(([title, text], i) => (
                <li key={title} className="flex gap-4 rounded-2xl border border-line bg-surface p-5">
                  <span className="grid size-8 shrink-0 place-items-center rounded-full bg-brand text-sm font-bold text-on-brand">{i + 1}</span>
                  <div><h3 className="font-display text-lg font-semibold">{title}</h3><p className="text-[15px] text-soft">{text}</p></div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* Why it's different */}
        <section className="py-20">
          <div className={wrap}>
            <h2 className={`${h2} max-w-2xl`}>Built for real conversations, not a generic chatbot.</h2>
            <div className="mt-10 grid gap-5 md:grid-cols-[1.3fr_1fr]">
              <div className="rounded-3xl bg-wash p-8">
                <ShieldCheck size={30} className="text-brand" aria-hidden />
                <h3 className="mt-3 font-display text-2xl font-semibold">Never plays doctor, lawyer or visa officer.</h3>
                <p className="mt-2 text-soft">It answers questions about your business and sends anything professional to your staff.</p>
              </div>
              <div className="rounded-3xl bg-wash-sun p-8">
                <Translate size={30} className="text-brand" aria-hidden />
                <h3 className="mt-3 font-display text-2xl font-semibold">Speaks like your customers.</h3>
                <p className="mt-2 text-soft">Bangla script, Banglish and English, and it switches when they switch.</p>
                <div className="mt-4 flex flex-wrap gap-2 text-[17px]">
                  <span lang="bn" className="rounded-2xl bg-surface px-3 py-1">ফি কত?</span>
                  <span lang="bn-Latn" className="rounded-2xl bg-surface px-3 py-1">Fee koto?</span>
                  <span className="rounded-2xl bg-surface px-3 py-1">What&apos;s the fee?</span>
                </div>
              </div>
              <div className="rounded-3xl border border-line bg-surface p-8">
                <Tray size={30} className="text-brand" aria-hidden />
                <h3 className="mt-3 font-display text-2xl font-semibold">One inbox.</h3>
                <p className="mt-2 text-soft">Messenger, WhatsApp, Telegram and website chats in one place.</p>
              </div>
              <div className="rounded-3xl border border-line bg-surface p-8">
                <RocketLaunch size={30} className="text-brand" aria-hidden />
                <h3 className="mt-3 font-display text-2xl font-semibold">Live in 5 working days.</h3>
                <p className="mt-2 text-soft">We write your knowledge, connect your Page and train your team.</p>
              </div>
            </div>
          </div>
        </section>

        {/* Pricing */}
        <section id="pricing" className="border-y border-line bg-sand py-20">
          <div className={wrap}>
            <h2 className={h2}>Simple monthly plans.</h2>
            <div className="mt-10 grid gap-6 md:grid-cols-3">
              {plans.map((p) => (
                <div key={p.name} className={`relative flex flex-col rounded-3xl bg-surface p-7 ${p.pick ? "ring-2 ring-brand" : "border border-line"}`}>
                  {p.pick && <span className="absolute -top-3 left-7 rounded-full bg-brand px-3 py-0.5 text-xs font-semibold text-on-brand">Most chosen</span>}
                  <h3 className="font-display text-xl font-semibold">{p.name}</h3>
                  <div className="mt-3 font-display text-4xl font-bold">{p.price} <span className="font-sans text-base font-normal text-soft">/ month</span></div>
                  <ul className="mt-5 grid gap-2.5 text-[15px] text-soft">
                    {p.items.map((it) => <li key={it} className="flex gap-2"><Check size={18} className="mt-0.5 shrink-0 text-brand" aria-hidden />{it}</li>)}
                  </ul>
                  <a href={wa(`Hi, I'm interested in the Halcyo ${p.name} plan.`)} target="_blank" rel="noopener"
                    className={`${btn} mt-7 ${p.pick ? "bg-brand text-on-brand" : "bg-sand hover:text-brand"}`}>Book a demo</a>
                </div>
              ))}
            </div>
            <p className="mt-6 text-sm text-soft">Setup ৳25,000 once. WhatsApp message fees are billed by Meta directly to you.</p>
            <div className="mt-6 flex flex-col items-start justify-between gap-5 rounded-3xl bg-wash-sun p-7 sm:flex-row sm:items-center">
              <div>
                <h3 className="font-display text-xl font-semibold">The first 2 businesses get setup free and 50% off for 3 months.</h3>
                <p className="mt-1 text-sm text-soft">We write your knowledge, connect your pages and test it with you.</p>
              </div>
              <a href={wa("Hi, I want the Halcyo pilot offer.")} target="_blank" rel="noopener" className={`${primary} shrink-0`}>Book a demo</a>
            </div>
          </div>
        </section>

        {/* FAQ */}
        <section id="faq" className="py-20">
          <div className={`${wrap} grid gap-10 lg:grid-cols-[.8fr_1.2fr]`}>
            <h2 className={h2}>Questions owners ask.</h2>
            <div>
              {faqs.map(([q, a]) => (
                <details key={q} className="group border-b border-line">
                  <summary className="flex cursor-pointer list-none justify-between gap-4 py-5 font-display text-lg font-semibold">
                    {q}<Plus size={20} className="mt-1 shrink-0 text-brand transition-transform group-open:rotate-45" aria-hidden />
                  </summary>
                  <p className="max-w-[62ch] pb-5 text-soft">{a}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        {/* Founder */}
        <section className="pb-20">
          <div className={`${wrap} flex flex-col items-start gap-5 sm:flex-row sm:items-center`}>
            <Image src={founder} alt="Md Radwan Ahamed, founder of Halcyo" placeholder="blur" sizes="80px"
              className="size-20 shrink-0 rounded-full object-cover ring-1 ring-line" />
            <div>
              <h3 className="font-display text-lg font-semibold">Md Radwan Ahamed, founder</h3>
              <p className="max-w-[62ch] text-soft">I&apos;m building Halcyo so small businesses in Bangladesh never lose a customer to a slow reply. Now onboarding our first pilot businesses.</p>
              <a href="https://radwanahamed.dev" target="_blank" rel="noopener" className="mt-1 inline-flex items-center gap-1 font-semibold text-brand hover:underline">
                radwanahamed.dev<ArrowUpRight size={16} aria-hidden />
              </a>
            </div>
          </div>
        </section>

        {/* Final CTA */}
        <section className="relative isolate overflow-hidden py-24 text-center">
          <AnimatedBackground />
          <div className="mx-auto max-w-2xl px-5">
            <h2 className="font-display text-4xl leading-tight font-bold sm:text-5xl">Your next customer is messaging tonight.</h2>
            <p className="mt-3 text-soft">Book a 15-minute demo. We&apos;ll show it answering your own questions.</p>
            <div className="mt-8 flex flex-wrap justify-center gap-3">
              <a href={BOOK} target="_blank" rel="noopener" className={primary}>Book a demo<ArrowRight size={18} aria-hidden /></a>
              <TryIt />
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-line py-9 text-[15px] text-soft">
        <div className={`${wrap} flex flex-wrap justify-between gap-5`}>
          <div>
            <div className="font-display text-xl font-bold text-ink">halcyo</div>
            <div>Calm days for busy teams. Dhaka, Bangladesh.</div>
            <div>Built on Claude by Anthropic.</div>
          </div>
          <div>
            <div>Questions: <a href="mailto:ask@halcyo.tech" className="text-ink hover:text-brand">ask@halcyo.tech</a></div>
            <div>Business: <a href="mailto:contact@halcyo.tech" className="text-ink hover:text-brand">contact@halcyo.tech</a></div>
          </div>
          <nav aria-label="Footer" className="flex gap-5">
            <a href="/privacy" className="hover:text-brand">Privacy</a>
            <a href="/terms" className="hover:text-brand">Terms</a>
            <a href={BOOK} target="_blank" rel="noopener" className="hover:text-brand">WhatsApp</a>
          </nav>
        </div>
      </footer>
    </>
  );
}
