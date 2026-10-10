# Halcyo frontend guide (Next.js)

**Date:** 2026-10-10 · **For:** the full revamp of halcyo.tech in Next.js, with real images and proper sections.
**Read with:** `LANDING_GUIDE.md` (audience, copy, anti-slop rules) and `HALCYO_DESIGN.md` (style reference; colors here replace its teal).
**Current live site:** `app/static/landing.html` on Vercel. Keep it live until the Next.js site passes the checklist in section 14, then switch the domain.

---

## 1. Principles (read first)

1. **One job:** a service-business owner in Bangladesh books a demo. Every section helps that or goes.
2. **Show, don't claim:** chat mockups, real photos of real Bangladeshi businesses, the real widget. No robots, orbs or stock offices.
3. **Calm and trustworthy:** mostly off-white and ink, cobalt only for things you can click.
4. **Mobile first:** most visitors come from a WhatsApp or Facebook link on an Android phone on 4G.
5. **Static by default:** every page is pre-rendered. Only the small interactive parts are client components.
6. **Honest:** no invented clients, numbers or testimonials (this matters for Claude Startups too).

---

## 2. Stack (versions checked on npm, 2026-10-10)

| What | Choice | Version |
|---|---|---|
| Framework | Next.js, App Router, TypeScript, Turbopack | `next@16.4.0` |
| Styling | Tailwind CSS v4 (tokens in CSS, no config file) | `tailwindcss@4.3.3` |
| Animation | Motion (`motion/react`) for the chat mockup and reveals | `motion@14.1.0` |
| Icons | Phosphor | `@phosphor-icons/react@2.1.10` |
| Fonts | `next/font/google`: Anek Bangla + Hind Siliguri | built in |
| Images | `next/image` with static imports | built in |
| Hosting | Vercel (same account as now) | |

**Not used (on purpose):** UI kits (shadcn, MUI), CSS-in-JS, i18n libraries, CMS, state libraries, GSAP, Three.js, Lottie. The site is about 10 sections of mostly static content; none of them earn their weight. Add one only with a written reason.

Pin exact versions in `package.json` (no `^`). Update on purpose, not by accident.

---

## 3. Setup

The Next.js app lives in a new `web/` folder in this repo. The Python backend stays where it is.

```bash
npx create-next-app@16.4.0 web --typescript --tailwind --app --src-dir --eslint --import-alias "@/*" --use-npm --disable-git --yes
```
```bash
cd web && npm install motion@14.1.0 @phosphor-icons/react@2.1.10 --save-exact
```

Delete the starter content (`page.tsx` body, `public/*.svg`, the default globals) before writing anything.

### Folder structure
```
web/
  src/
    app/
      layout.tsx            # fonts, metadata, <html lang>, theme tokens
      page.tsx              # homepage: just puts the sections in order
      globals.css           # Tailwind import + design tokens (section 4)
      privacy/page.tsx      # ported from app/static/privacy.html
      terms/page.tsx        # ported from app/static/terms.html
      [industry]/page.tsx   # /study-abroad, /pet-care, /clinic, /law-firm
      opengraph-image.tsx   # share image (section 11)
      sitemap.ts  robots.ts
    sections/               # one file per page section (section 6)
      Hero.tsx  Problem.tsx  Industries.tsx  HowItWorks.tsx  Different.tsx
      Pricing.tsx  Faq.tsx  Founder.tsx  FinalCta.tsx  Nav.tsx  Footer.tsx
    components/             # small reusable pieces
      Button.tsx  ChatMockup.tsx  AnimatedBackground.tsx  Section.tsx
    content/
      site.ts               # ALL copy, chats, plans, FAQs, links (section 5)
    images/                 # source photos, imported statically (section 8)
  public/                   # only favicon, icons, files that need a fixed URL
```

Rules: one section per file; no section over ~120 lines; no copy inside components (it comes from `content/site.ts`).

---

## 4. Design tokens (Tailwind v4)

`src/app/globals.css`:
```css
@import "tailwindcss";

@theme {
  --color-brand: #2453D6;      /* cobalt: buttons, links, active tab only */
  --color-on-brand: #FFFFFF;
  --color-sun: #F6A43C;        /* marigold: "Booked"/"Hot" badges only, never text on light */
  --color-ink: #16181D;
  --color-soft: #4B5060;
  --color-bg: #F7F7F5;
  --color-surface: #FFFFFF;
  --color-wash: #EAF0FF;       /* bot bubbles, tinted tiles */
  --color-wash-sun: #FDF0DC;   /* one tile + pilot offer */
  --color-line: #E3E3DF;

  --font-display: var(--font-anek), var(--font-hind), system-ui, sans-serif;
  --font-body: var(--font-hind), system-ui, sans-serif;

  --radius-card: 20px;
  --shadow-lift: 0 1px 2px rgb(22 24 29 / .04), 0 12px 32px rgb(36 83 214 / .10);
}

@media (prefers-color-scheme: dark) {
  :root {
    --color-brand: #8EAAFF; --color-on-brand: #0E1015;
    --color-ink: #ECEDEF; --color-soft: #A3A8B5;
    --color-bg: #0E1015; --color-surface: #171A21;
    --color-wash: #1C2440; --color-wash-sun: #33291A; --color-line: #262A33;
    --shadow-lift: 0 20px 50px rgb(0 0 0 / .4);
  }
}

body { background: var(--color-bg); color: var(--color-ink); font-family: var(--font-body); }
:lang(bn) { line-height: 1.7; }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
```
Use them as `bg-brand`, `text-soft`, `bg-wash`, `rounded-card`, `shadow-lift`, `font-display`.

Contrast (checked): white on brand 6.4:1 · brand on bg 6.0:1 · ink on bg 16.6:1 · soft on bg 7.5:1 · dark-mode brand on dark bg 8.5:1 · ink on sun 8.7:1.

**Shape rule:** buttons, chips, tabs and badges are `rounded-full`; cards, images and chat bubbles use `rounded-card` (20px), images inside cards 16px. Nothing else.

### Fonts: `src/app/layout.tsx`
```tsx
import { Anek_Bangla, Hind_Siliguri } from "next/font/google";
import type { Metadata } from "next";
import "./globals.css";

const anek = Anek_Bangla({ subsets: ["bengali", "latin"], weight: ["500", "600", "700"], variable: "--font-anek" });
const hind = Hind_Siliguri({ subsets: ["bengali", "latin"], weight: ["400", "500", "600"], variable: "--font-hind" });

export const metadata: Metadata = {
  metadataBase: new URL("https://halcyo.tech"),
  title: { default: "Halcyo: every customer message answered", template: "%s · Halcyo" },
  description: "Halcyo replies on Messenger, WhatsApp and your website in Bangla, Banglish or English, and books appointments for you.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${anek.variable} ${hind.variable}`}>
      <body>{children}</body>
    </html>
  );
}
```
`next/font` self-hosts the files, so there is no request to Google from visitors' phones.

### Type scale
| Use | Classes |
|---|---|
| Hero headline | `font-display font-semibold text-[38px] md:text-5xl lg:text-[60px] leading-[1.08]` (max 3 lines) |
| Section title | `font-display font-semibold text-3xl md:text-[42px] leading-[1.15] max-w-[22ch]` |
| Card title | `font-display font-semibold text-xl md:text-2xl` |
| Body | `text-[17px] md:text-lg leading-relaxed text-soft max-w-[62ch]` |
| Small | `text-sm text-soft` |

---

## 5. Content lives in one file

`src/content/site.ts` holds every visible string, so copy changes never touch layout code, and a Bangla version later is one more object.

```ts
export const site = {
  whatsapp: "8801966163995",
  widgetOrigin: "", // e.g. "https://app.halcyo.tech" once the backend is live; empty hides "Try it"
  hero: {
    title: "Every customer message answered.",
    titleAccent: "Even at 11 pm.",
    lead: "Halcyo replies on Messenger, WhatsApp and your website in Bangla, Banglish or English, and books appointments for you.",
  },
  chats: [/* the 4 industry conversations from app/static/landing.html */],
  plans: [/* Starter, Growth, Scale from PRD §14.1 */],
  faqs: [/* 6 questions */],
} as const;

export const bookHref = `https://wa.me/${site.whatsapp}?text=${encodeURIComponent("Hi, I saw Halcyo and want a demo.")}`;
```
Copy rules (no em dashes, banned words, no invented numbers, one label per intent) are in `LANDING_GUIDE.md` §7. CTA labels: **"Book a demo"** and **"Try it"**, nothing else.

---

## 6. Page sections (the revamp)

Ten sections, each a different layout. Background alternates `bg` / `surface` to separate them; no lines between every section.

| # | Section | Layout | Image / visual | Client JS? |
|---|---|---|---|---|
| 0 | **Nav** | logo, 4 links, CTA; sticky, 64px | logo | no |
| 1 | **Hero** | split: text left, visual right; animated background | **photo** of a business owner/staff with a phone (4:5) + **ChatMockup** overlapping its bottom-left corner | ChatMockup only |
| 2 | **Problem** | one band, 3 short lines in a row | none (text is the point) | no |
| 3 | **Industries** | tabs + panel | per tab: **photo** of that business (3:2) + finished chat + *They ask / Halcyo does / Never does* | tabs only |
| 4 | **Live demo** | full-width tinted panel | the real widget, opened (only when `widgetOrigin` is set; otherwise the section is skipped) | widget |
| 5 | **How it works** | sticky title left, timeline right | small **inbox/lead card** visual next to "Alerts" (screenshot once the inbox exists, until then a ChatMockup-style card) | no |
| 6 | **Why it's different** | 2×2 asymmetric grid | 1 tile with a **photo** (owner reading phone at night), 1 tile with Bangla/Banglish/English chips | no |
| 7 | **Pricing** | 3 plans + pilot offer box | none | no |
| 8 | **FAQ** | title left, `<details>` list right | none | no (native `<details>`) |
| 9 | **Founder** | photo + 2 lines + LinkedIn | **real photo of you** (1:1) | no |
| 10 | **Final CTA** | centered, animated background | none | no |
| 11 | **Footer** | logo, line, links, "Built on Claude by Anthropic." | none | no |

Industry pages (`/study-abroad` etc.) reuse the same sections with that industry's content, without the Industries tabs (`generateStaticParams` over the 4 slugs).

### Section wrapper
```tsx
// components/Section.tsx
export function Section({ id, tone = "bg", children }: { id?: string; tone?: "bg" | "surface"; children: React.ReactNode }) {
  return (
    <section id={id} className={`${tone === "surface" ? "bg-surface" : ""} py-18 lg:py-26`}>
      <div className="mx-auto max-w-[1200px] px-5 md:px-8">{children}</div>
    </section>
  );
}
```

### Hero layout sketch
```
desktop (≥1024)                              phone (375)
┌──────────────────────┬─────────────────┐   ┌───────────────┐
│ Headline (3 lines)   │  ┌───────────┐  │   │ Headline      │
│ Lead (≤20 words)     │  │  PHOTO    │  │   │ Lead          │
│ [Book a demo][Try it]│  │  4:5      │  │   │ [Book a demo] │
│                      │ ┌┴──────┐    │  │   │ PHOTO (4:5)   │
│                      │ │ CHAT  │────┘  │   │  └ CHAT card  │
└──────────────────────┴─┴───────┴───────┘   └───────────────┘
```

---

## 7. Key components

### Button (server component)
```tsx
import Link from "next/link";
const base = "inline-flex min-h-12 items-center justify-center gap-2 rounded-full px-6 font-semibold whitespace-nowrap transition active:translate-y-px focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-brand";
export function Button({ href, variant = "primary", children }: { href: string; variant?: "primary" | "ghost"; children: React.ReactNode }) {
  const look = variant === "primary" ? "bg-brand text-on-brand hover:brightness-95" : "bg-surface text-ink ring-1 ring-inset ring-line";
  return <Link href={href} className={`${base} ${look}`}>{children}</Link>;
}
```

### ChatMockup (client component)
- Props: `chat` (from `site.chats`), `autoplay` (hero true, tabs false).
- Steps: time stamp → customer bubble → typing dots (~1 s) → bot reply → chips → chosen chip → confirmation with marigold **Booked** badge → wait 4 s → next industry.
- Use `motion` for the bubble entrance (`initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}`), timers in one `useEffect` with cleanup.
- `useReducedMotion()` → render the finished conversation, no timers.
- Pause when `document.hidden`.
- Messages are real text with `lang` set (`bn`, `bn-Latn`, `en`), never images.
- Fixed height (`min-h-[420px]`) so the page doesn't jump while it plays (CLS).
- The existing logic in `app/static/landing.html` (`play()`) is the reference; port it, don't redesign it.

### AnimatedBackground (server component, CSS only)
Two blurred circles (`bg-brand/15`, `bg-sun/20`, `blur-3xl`, 560px) drifting on 28-32 s `ease-in-out infinite alternate` keyframes, plus 8-10 faint speech-bubble outlines rising (CSS keyframes, random-looking delays written as inline styles). Hero and final CTA only, `absolute inset-0 -z-10 pointer-events-none overflow-hidden`. Total effect under 25% opacity. No canvas, no JS.

### IndustryTabs (client component)
`role="tablist"`, arrow keys move between tabs, `aria-selected`, roving `tabIndex`. Switching swaps the photo, the finished chat and the three text blocks; fade 150 ms.

### FAQ
Native `<details>/<summary>`, no JS. Phosphor `Plus` icon rotates 45° when open.

### Live widget
```tsx
"use client";
import Script from "next/script";
export function LiveWidget({ origin }: { origin: string }) {
  if (!origin) return null;
  return <Script src={`${origin}/widget.js`} data-company="demo" strategy="lazyOnload" />;
}
```
"Try it" calls `document.querySelector("chat-widget")?.shadowRoot?.querySelector(".launch")?.click()`. Add `https://halcyo.tech` to the demo tenant's allowed origins when the backend goes live.

---

## 8. Images (the main part of the revamp)

### 8.1 What to shoot or source (shot list)

| Slot | Content | Ratio · export size | Notes |
|---|---|---|---|
| `hero.jpg` | A young staff member at a front desk in a Dhaka office, smiling at a phone, evening light | 4:5 · 1200×1500 | The hero image. Real place, real person. |
| `ind-study-abroad.jpg` | Counsellor and student at a desk with brochures / laptop | 3:2 · 1500×1000 | |
| `ind-pet-care.jpg` | Groomer or vet with a cat or dog | 3:2 · 1500×1000 | |
| `ind-clinic.jpg` | Doctor's chamber reception with patients waiting (faces not identifiable) | 3:2 · 1500×1000 | No white-coat-with-tablet stock look. |
| `ind-law-firm.jpg` | Lawyer's desk with files, or a consultation across a desk | 3:2 · 1500×1000 | |
| `night-phone.jpg` | Hand holding a phone with a chat open, warm room light at night | 4:5 · 1000×1250 | For the "Why it's different" tile. |
| `founder.jpg` | You, plain background, natural light | 1:1 · 800×800 | Real photo only. Strong trust signal. |
| `og.png` | Share image (generated in code, see 11) | 1200×630 | |

**Best source, in order:**
1. **Your own photos** at real businesses (ask a friendly consultancy, vet or chamber; 30 minutes each). Get written permission from every person who is recognisable.
2. **AI-generated images**, made to the same brief, when you can't shoot. Never for the founder photo, never presented as real clients.
3. **Stock** from Unsplash/Pexels only when it clearly shows South Asian people in a believable local setting. Check the licence.

### 8.2 One look for every photo
- Natural light, warm but not orange; slightly lifted shadows; no heavy filters.
- People mid-action (talking, typing, handing over), not posing at the camera.
- Clean backgrounds, a hint of cobalt or marigold somewhere is a bonus, never forced.
- Same color grade on all images (apply one preset in Lightroom/Snapseed to the whole set).
- No text inside images, no logos of other companies, no visible phone numbers.

### 8.3 Prompt template for AI images
```
Documentary-style photo, Dhaka, Bangladesh. [SCENE: e.g. a young receptionist at a small
pet-care clinic smiling while replying to a message on her phone, a groomed cat on the
counter]. Natural window light, early evening, warm but neutral color, shallow depth of
field, 35mm lens, realistic skin and fabrics, modest modern clothing, uncluttered
background. No text, no logos, no watermark. Aspect ratio [4:5 / 3:2].
```
Reject any result with warped hands, fake text, gibberish signs, or a "stock photo" smile. Generate 6-8, pick 1.

### 8.4 Files and code
- Put source images in `src/images/`, **import them statically** so Next.js knows the size and makes a blur placeholder:
```tsx
import Image from "next/image";
import hero from "@/images/hero.jpg";

<Image src={hero} alt="Receptionist at a Dhaka pet clinic replying to a customer on her phone"
  placeholder="blur" priority sizes="(min-width: 1024px) 520px, 100vw"
  className="rounded-card object-cover" />
```
- `priority` on the hero image only. Everything else lazy-loads by default.
- Always pass `sizes` (otherwise phones download desktop sizes).
- Export JPGs at quality ~80 before adding; keep each source under 400 KB. Next.js serves AVIF/WebP automatically; add `images: { formats: ["image/avif", "image/webp"] }` in `next.config.ts`.
- **Alt text** says what's happening, in one sentence. Decorative images get `alt=""`.
- File names: lowercase, hyphens, describe the slot (`ind-pet-care.jpg`).

---

## 9. Motion rules

| Allowed | Where |
|---|---|
| Animated background (drift + rising bubbles) | hero, final CTA |
| Chat mockup playing | hero |
| Fade + 12px rise when a section's main element enters the viewport, once | max one element per section (`whileInView`, `viewport={{ once: true }}`) |
| Tab switch fade 150 ms, button press 1px, FAQ icon rotate | everywhere |

Not allowed: parallax, scroll-jacking, marquees, mouse-following effects, counters ticking up, infinite pulses. Everything respects `prefers-reduced-motion`. Animate only `transform` and `opacity`.

---

## 10. Accessibility (must pass)

- Every interactive element reachable by keyboard, visible focus ring (`outline-brand`, 3px).
- Tap targets ≥ 44px. Buttons ≥ 48px tall.
- Contrast AA in both modes (tokens in section 4 already pass; don't introduce new text colors).
- `lang="bn"` / `lang="bn-Latn"` on Bangla and Banglish text.
- One `<h1>` per page; sections use `<h2>`; landmarks: `<header>`, `<main>`, `<footer>`, `<nav aria-label>`.
- Chat mockup: `aria-live` off (it's decorative motion), but its text stays readable; give the container `aria-label="Example conversation"`.

---

## 11. SEO and sharing

- `metadata` per page (title ≤ 60 chars, description ≤ 155).
- `src/app/opengraph-image.tsx` with `ImageResponse` from `next/og`: off-white background, the headline in Anek Bangla, small cobalt logo. 1200×630.
- `sitemap.ts` and `robots.ts` (allow all, point to the sitemap).
- JSON-LD `Organization` in the homepage: name, url, logo, `contactPoint` (WhatsApp), `areaServed: "BD"`.
- Canonical URL `https://halcyo.tech` (Vercel redirects `www` to the apex; set it in the Vercel domain settings).

---

## 12. Performance budget

| Metric | Target (mobile, 4G) |
|---|---|
| LCP (hero image) | < 2.0 s |
| CLS | < 0.05 |
| INP | < 150 ms |
| JS sent to the browser | < 90 KB gzipped for the homepage |
| Total page weight on first load | < 700 KB |

How: server components by default; `"use client"` only in ChatMockup, IndustryTabs, LiveWidget; hero image `priority` + `sizes`; fonts via `next/font`; no third-party scripts except the widget (lazy). Check with Lighthouse (mobile) and Vercel Speed Insights.

---

## 13. Deploy (Vercel)

1. Push the repo to GitHub (private).
2. In Vercel, **create a new project** from the repo, **Root Directory: `web`**, framework Next.js. Every push to `main` deploys; branches get preview URLs.
3. Check the preview URL against section 14.
4. Move the domains: in Vercel, remove `halcyo.tech` and `www.halcyo.tech` from the old static `halcyo` project and add them to the new one. DNS in Cloudflare stays the same (the CNAMEs point to Vercel, not to a project), still **DNS only** (grey cloud).
5. Port `/privacy` and `/terms` **before** the switch, so those links never break.
6. Then delete the old static project, plus `app/static/landing.html`, `vercel.json` and `.vercelignore`.

Optional: `@vercel/analytics` for page views (no cookies, so no consent banner needed).

---

## 14. Done checklist (every page)

- [ ] Matches `LANDING_GUIDE.md` §7 (no em/en dashes, no banned words, no invented numbers, one label per intent).
- [ ] All copy comes from `content/site.ts`.
- [ ] Every image is real or labelled honestly, has alt text, `sizes`, and the same color grade.
- [ ] Hero fits a 375×812 phone with the CTA visible.
- [ ] Light and dark mode both checked.
- [ ] Keyboard-only walk-through works; focus always visible.
- [ ] Reduced motion: nothing moves, chat shows finished.
- [ ] Lighthouse mobile: Performance ≥ 90, Accessibility 100, SEO 100.
- [ ] `/privacy` and `/terms` live; WhatsApp link opens the right number.
- [ ] Bangla lines read by a native speaker.
- [ ] `npm run build` has no warnings; `npm run lint` clean.

---

## 15. Using Claude Code for the build

Work one section at a time. Paste prompts like:
```
Read FRONTEND_GUIDE.md and LANDING_GUIDE.md. Set up web/ exactly as sections 2-5 say.
Don't add any package not listed. Show me the folder tree when done.
```
```
Build sections/Hero.tsx per FRONTEND_GUIDE.md §6-8: photo src/images/hero.jpg (4:5), ChatMockup
overlapping its bottom-left, AnimatedBackground behind. Port the chat logic from
app/static/landing.html. Then screenshot it at 1280×800 and 375×812, light and dark.
```
```
Review the whole page against FRONTEND_GUIDE.md §14 and LANDING_GUIDE.md §7. List every
failure first, then fix them.
```

---

## Sources
- [Next.js blog (16.x releases)](https://nextjs.org/blog?page=1)
- [Next.js release notes (releases.sh)](https://releases.sh/vercel/nextjs.md)
- Package versions: `npm show next | tailwindcss | motion | @phosphor-icons/react version`, run 2026-10-10.
