# Halcyo: Style Reference
> Calm teal on cool mist: one teal action color, a live-looking chat mockup, a slow animated background, Bangla-ready type.

**Theme:** light and dark (light by default, follows the system setting)

Built for Claude Design from two Refero styles, with Halcyo's own colors and fonts:
- **Lens** ([refero](https://styles.refero.design/style/63c0e759-3175-4f62-a8e3-b9e285f9e998)): calm white canvas, almost no color, **one** teal action color, pill buttons, 16px cards.
- **Calendly** ([refero](https://styles.refero.design/style/9946887b-ffa9-4276-af81-ae6352795afb)): a booking product like Halcyo. Split hero with a **real product card** on the right, tinted shadows, flat surfaces with no gradients.
- Considered and not used: 2.AG (dark teal and mint; option for a dark hero), Chat for impact (too many pastels), Workable (violet), Ease Health (green only), Zendesk (lime).

What changed from the references, and why:
- Lens's teal `#00caa0` with white text has a contrast of about 2:1 and fails accessibility. Halcyo uses a deeper teal, `#0B6E78` (6:1).
- Lens uses Saans + Inter and Calendly uses Gilroy. Neither supports Bangla. Halcyo uses **Anek Bangla + Hind Siliguri**.
- Calendly puts magenta and cyan blobs behind its screenshots. Halcyo uses a flat Teal Wash panel behind the chat mockup, and puts all movement in one animated background instead.
- Lens uses four pastel tiles (peach, mint, lavender, periwinkle). Halcyo uses two tints from its own colors only.

## Tokens: Colors

| Name | Light | Dark | Token | Role |
|---|---|---|---|---|
| Teal | `#0B6E78` | `#5FC6CC` | `--brand` | The **only** action color: filled CTAs, links, active tab. Never decoration. |
| On Teal | `#FFFFFF` | `#0F1A1F` | `--on-brand` | Text on Teal buttons |
| Marigold | `#F6A43C` | `#F6A43C` | `--sun` | Highlights only: "Hot lead" / "New booking" badge, one logo detail. Max 3 per page. Never text on light. |
| Ink | `#17242B` | `#E8EFEE` | `--ink` | Headings and body text. Never pure black. |
| Ink Soft | `#4A5B63` | `#9DB0B5` | `--ink-soft` | Sub-headlines, helper text, captions |
| Mist | `#F5F8F7` | `#0F1A1F` | `--bg` | Page canvas |
| Paper | `#FFFFFF` | `#16242B` | `--surface` | Cards, chat bubbles, nav |
| Teal Wash | `#E3F1F1` | `#1B3036` | `--wash-teal` | Panel behind the chat mockup, bot chat bubbles, icon circles |
| Marigold Wash | `#FDF0DC` | `#33291A` | `--wash-sun` | One feature tile and the pilot-offer box only |
| Line | `#DCE5E4` | `#26363D` | `--line` | Hairline borders, dividers |

Contrast: Teal on Mist 5.6:1 · white on Teal 6.0:1 · Ink on Mist 14.9:1 · Ink Soft on Mist 6.6:1 · dark Teal on dark Mist 8.8:1 · Ink on Marigold 7.8:1. All pass WCAG AA.

## Tokens: Typography

### Anek Bangla: display and headings (`--font-display`)
- Google Fonts, Latin + Bangla. Weights 500, 600. Slightly wide, warm, friendly.
- Sizes: 56px hero (desktop), 40px hero (mobile), 36px section title, 22px card heading, 18px small heading.
- Line height 1.1 for hero, 1.2 for headings. Bangla headings 1.3.
- Letter spacing 0. Don't tighten it: it hurts Bangla.

### Hind Siliguri: body and UI (`--font-body`)
- Google Fonts, Latin + Bangla. Weights 400, 500, 600.
- Sizes: 18px body (desktop), 17px body (mobile), 16px UI and buttons, 14px captions.
- Line height 1.6 for body, 1.7 for Bangla body. Max 65 characters per line.

### Type scale

| Role | Family | Weight | Size | Line height | Token |
|---|---|---|---|---|---|
| caption | Hind Siliguri | 400 | 14px | 1.5 | `--text-caption` |
| body | Hind Siliguri | 400 | 18px | 1.6 | `--text-body` |
| button | Hind Siliguri | 600 | 16px | 1 | `--text-button` |
| heading-sm | Anek Bangla | 600 | 22px | 1.25 | `--text-heading-sm` |
| heading | Anek Bangla | 600 | 36px | 1.2 | `--text-heading` |
| display | Anek Bangla | 600 | 56px | 1.1 | `--text-display` |

## Tokens: Spacing and shapes

**Base unit:** 8px · **Density:** comfortable

Spacing: 8, 16, 24, 32, 48, 64, 96px. Section gap 96px desktop, 64px mobile. Card padding 24-32px. Element gap 16px.

| Element | Radius |
|---|---|
| buttons, chips, tabs, badges | 999px (pill) |
| cards, screenshot frames, chat bubbles, inputs | 16px |

Nothing else. No 4px or 8px corners anywhere.

### Shadows (teal-tinted, never black)

| Name | Value | Use |
|---|---|---|
| hairline | `0 0 0 1px rgb(11 110 120 / .08)` | cards on Mist |
| lift | `0 4px 6px rgb(11 110 120 / .04), 0 12px 24px rgb(11 110 120 / .06), 0 30px 50px rgb(11 110 120 / .08)` | chat mockup card only |

### Layout
- Max width 1200px, centered. Side padding 16px mobile, 24px tablet, 32px desktop.
- Nav 64px, sticky, Paper background with a hairline bottom border.

## Components

### Primary button (pill)
Teal fill, white text, Hind Siliguri 16px 600, padding 14px × 24px, pill radius, min height 48px. Label: **"Book a demo"** only. Press: moves down 1px. Focus: 3px Teal outline, 2px offset.

### Secondary button (ghost pill)
Paper fill, 1px Line border, Ink text, same size. Label: **"Try it"** only.

### Top nav
Logo left (a simple speech-bubble mark with an "h" inside, in Teal, + "halcyo" lowercase), links center (How it works · Industries · Pricing · FAQ) in Hind Siliguri 16px 500 Ink, primary button right. One line. Mobile: logo + button + menu icon.

### Split hero (from Calendly)
Left column (≈ 55%): headline (display, max 2 lines), sub (body, Ink Soft, ≤ 20 words), button row (primary + secondary). Right column (≈ 45%): **Chat mockup**. Behind everything: the **Animated background**. Mobile: text, buttons, then the product card under them. Top padding ≤ 96px. Nothing else in the hero.

### Chat mockup (built in HTML, replaces Calendly's booking widget card)
A phone-shaped Paper card (16px radius, "lift" shadow, about 340 × 640px) on a flat Teal Wash panel offset by 24px behind it. Inside: a header (business name + a small "Replies instantly" line in Ink Soft), then a conversation that **plays itself**:
1. Customer bubble appears (time stamp 11:42 pm).
2. Bot "typing" dots for about 1 second.
3. Bot answer appears.
4. Quick-reply chips appear (e.g. "Book a session", "Talk to a person").
5. Customer taps a chip, bot confirms a booking with a Marigold "Booked" badge.
6. Pause 4 seconds, fade out, play the next industry's conversation.

Conversations (real-sounding Banglish, one per industry, rotate):
- Study abroad: "UK te IELTS 6 hole hobe? Total koto lagbe?" → answer with a fee range from the knowledge + offer of a counselling session.
- Pet care: "Persian cat er grooming koto? Kal sokale slot ache?" → price + 3 time chips.
- Clinic: "Dr. Rahman er serial kal er jonno pabo?" → 3 time chips, "Bring your old prescription."
- Law firm: "Jomi niye case, consultation fee koto?" → fee + "A lawyer will review your matter in the consultation."

Messages are text in HTML (selectable, readable by screen readers), not images. Under reduced motion: show the finished study-abroad conversation, no animation.

### Animated background (hero and final CTA only)
Calm, slow and behind the content. Two layers, CSS only:
1. **Soft light:** two large blurred circles, one Teal Wash (`#E3F1F1`) and one Marigold Wash (`#FDF0DC`), drifting slowly across the Mist canvas on a 24-30 second loop (transform only).
2. **Rising bubbles:** 8-12 faint speech-bubble outlines (1px Teal at 10-15% opacity, 24-64px) floating slowly upward and fading out, each with a different speed and delay (18-40 seconds).

Rules: total effect never above 25% opacity, so text contrast stays the same as on plain Mist. Animate only `transform` and `opacity`. Pause it when the tab is hidden. Under `prefers-reduced-motion`, show the still first frame. Dark mode: the same layers with the dark Teal Wash and Marigold Wash values. The rest of the page stays flat.

### Chat bubble
Customer: Paper, Ink text, right side. Bot: Teal Wash, Ink text, left side. 16px radius, 12px × 16px padding, Hind Siliguri 16px. Time stamp 12px Ink Soft. Appear one by one on scroll (fade + 8px rise, 300ms), static under reduced motion.

### Industry tabs
Pill tabs with a Phosphor icon + label (Student, PawPrint, Stethoscope, Scales). Active: Teal fill, white text. Inactive: Paper, Ink, Line border. All four tabs are equal. Mobile: horizontal scroll row. One panel below: *They ask* · *Halcyo does* · *Never does*. Switching a tab also switches the chat mockup to that industry's conversation.

### Feature tile (from Lens's feature card)
Paper card, 16px radius, hairline shadow, 32px padding. A 48px Teal Wash circle holding a 24px Phosphor icon in Teal, then heading-sm in Ink, then body in Ink Soft. Used in an **asymmetric** grid (2 large tiles with small chat mockups + 2 small text tiles), never 3 equal tiles in a row. One tile may use Marigold Wash.

### Timeline row ("How it works")
Vertical line in Line color on the left, a Teal dot per row, verb as the heading ("Answers", "Learns", "Scores", "Books", "Alerts", "Hands over"), one sentence of body. No cards, no "Step 1".

### Lead card
Paper card with a Marigold "Hot" pill badge (Ink text), the customer's name, 3 profile facts and the source ad. Real screenshot from the inbox once it exists.

### Pricing card
Paper, 16px radius, hairline. The Growth card gets a 2px Teal border and a small "Most chosen" text label (no badge colors). Price in display 40px. Pilot offer box below the plans in Marigold Wash.

### FAQ accordion
Rows separated by one Line hairline. Question in heading-sm, plus/minus icon in Teal. Answer body in Ink Soft.

### Footer
Mist background, logo, the one-line name story, links (Privacy · Terms · WhatsApp · email) in Ink Soft 14px. No version numbers.

## Do's and Don'ts

### Do
- Use Teal only for things you can click. If it's teal, it's an action.
- Use the chat mockup as the main visual. It shows the product working.
- Keep the page flat except for the animated background: Mist canvas, Paper cards, teal-tinted shadows only.
- Use pill shape for everything clickable and 16px for everything that holds content.
- Use a different layout for each section: split hero, text band, tabs, full-width demo, timeline, asymmetric tiles, pricing, accordion.
- Check every Bangla line for clipped vowel signs (ি ী ু ূ).

### Don't
- No gradients or soft light outside the animated background. No glow, glassmorphism or AI illustrations (robots, brains, sparkles).
- No purple or neon in the animated background. No fast, bouncy or mouse-following motion.
- No black shadows, no pure black `#000`.
- No Marigold text on light backgrounds (1.9:1, fails).
- No colors per industry. Industries show by icon, words and screenshot.
- No 3 equal cards in a row, no eyebrow labels on every section, no "01 / 02" numbers.
- No em dashes (—) or en dashes (–) in page copy.
- No fake numbers, testimonials or client logos.

## Agent Prompt Guide

**Quick color reference**
- text: `#17242B` (Ink) · secondary text: `#4A5B63` (Ink Soft)
- background: `#F5F8F7` (Mist) · cards: `#FFFFFF` (Paper)
- action: `#0B6E78` (Teal), white text
- highlight: `#F6A43C` (Marigold), Ink text, badges only
- tints: `#E3F1F1` (Teal Wash), `#FDF0DC` (Marigold Wash)
- border: `#DCE5E4` (Line)

**Example prompts**
1. *Hero:* Mist background, 2 columns. Left: "Every customer message answered. Even at 11 pm." in Anek Bangla 56px 600 Ink, line height 1.1; sub in Hind Siliguri 18px Ink Soft; buttons "Book a demo" (Teal pill) and "Try it" (ghost pill). Right: the chat mockup that plays the study-abroad conversation, in a phone-shaped Paper card, 16px radius, lift shadow, on a Teal Wash panel offset 24px. Behind: the animated background.
2. *Feature tile:* Paper, 16px radius, 32px padding, hairline shadow. 48px Teal Wash circle with a 24px Teal Phosphor icon, heading Anek Bangla 22px 600 Ink, body Hind Siliguri 16px Ink Soft.
3. *Industry tabs:* pill tabs with Phosphor icons; active tab Teal fill with white text; panel below with three short blocks; the chat mockup switches to that industry.

## Quick start

```css
:root {
  --brand: #0B6E78; --on-brand: #FFFFFF; --sun: #F6A43C;
  --ink: #17242B; --ink-soft: #4A5B63;
  --bg: #F5F8F7; --surface: #FFFFFF;
  --wash-teal: #E3F1F1; --wash-sun: #FDF0DC; --line: #DCE5E4;
  --font-display: "Anek Bangla", "Hind Siliguri", system-ui, sans-serif;
  --font-body: "Hind Siliguri", "Noto Sans Bengali", system-ui, sans-serif;
  --radius-pill: 999px; --radius-card: 16px;
  --shadow-hairline: 0 0 0 1px rgb(11 110 120 / .08);
  --shadow-lift: 0 4px 6px rgb(11 110 120 / .04), 0 12px 24px rgb(11 110 120 / .06), 0 30px 50px rgb(11 110 120 / .08);
}
@media (prefers-color-scheme: dark) {
  :root {
    --brand: #5FC6CC; --on-brand: #0F1A1F;
    --ink: #E8EFEE; --ink-soft: #9DB0B5;
    --bg: #0F1A1F; --surface: #16242B;
    --wash-teal: #1B3036; --wash-sun: #33291A; --line: #26363D;
    --shadow-hairline: 0 0 0 1px rgb(255 255 255 / .06);
    --shadow-lift: 0 20px 50px rgb(0 0 0 / .35);
  }
}
```
