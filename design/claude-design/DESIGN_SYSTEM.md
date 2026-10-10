Shop sign: friendly, local, loud where it counts. Baloo Da 2 for everything, warm grey by day and a navy dusk gradient by night, one Marigold panel per section, and a hero chat that answers in full Bangla, Banglish and English.

## Content

- Write like a person texting a busy owner: short sentences, concrete nouns, "you" and "your customers". Booking word on the homepage: "appointment".
- One label per intent: "Book a demo" and "Try it". Nothing else.
- Bangla leads where it matters: a Bangla line above the hero headline ("রাত ১১টায়ও উত্তর।") and above the final CTA. A native speaker reads every Bangla and Banglish line before publishing.
- Real copy: "Every customer message answered. Even at 11 pm." · "Made for businesses that sell time, care or advice." · "Your next customer is messaging tonight." · "Calm days for busy teams."
- No em or en dashes. No banned words (revolutionize, seamless, elevate, unleash, empower, next-gen, cutting-edge, game-changer, supercharge, harness, unlock, leverage, effortless, magic, "AI-powered").
- No invented numbers, testimonials, ratings or client logos. The example chat's price is a placeholder until a pilot client gives a real one.
- No guarantees or professional advice in any industry; each industry says what the bot never says.

## Color

- Two themes: `day` (default) and `night`, switched by the 44px toggle in the nav.
- Day: `bg` warm grey, `surface` white, `ink` near-black, black `btn-bg`.
- Night: the page background is a dusk gradient, not a flat colour: `linear-gradient(175deg, #0B1424 0%, #122039 38%, #1A2342 68%, #2E2430 88%, #3A2A22 100%)` with a Marigold glow top right (`radial-gradient(1000px 640px at 88% 0%, rgba(246,164,60,.20), transparent 62%)`) and a blue haze left (`radial-gradient(900px 700px at 0% 55%, rgba(64,96,170,.22), transparent 65%)`). `bg` is its top colour. Cards are navy `surface`; buttons turn Marigold.
- `panel` (Marigold) is the brand moment: the hero panel, the live demo panel, one feature card, the pilot offer, the marquee dots and the Booked badge. Text on it is always `on-panel`. At most one Marigold block per section.
- `accent-text` for a highlighted phrase; never plain Marigold text on the day canvas.
- No teal, no purple, no neon, no gradient text, no glassmorphism. The night gradient is the only gradient.

## Type

- Baloo Da 2 (Google Fonts, Latin and Bangla in one family): `display` 76px/800, `heading` 52px/800, `heading-sm` 28px/800, `lead` 21px/500, `body` 18px, `chat` 17px/500, `button` 18px/700, `label` 13px uppercase.
- Tight leading on headlines (0.98 to 1); body 1.45 to 1.55; Bangla body 1.7. Check vowel signs (ি ী ু ূ).
- Phones: hero 46px, section titles 34px.

## Shape and layout

- Rounded and chunky: `radius-button` 12px, `radius-bubble` 14px, `radius-card` 24px, `radius-panel` 28px. No shadows; cards sit on the canvas by colour.
- Max width 1280px, 56px gutter (20px on phones), sections open with 88px.
- Page order: hero (text left, Marigold panel with photo and chat right) → businesses-we-serve strip → three problem cards → industry tabs → live demo panel → How it works rows → feature cards → plan cards and pilot offer → FAQ → founder → black CTA block → footer.

## Imagery

- Hero: a real photo of a person reading a reply on a phone, behind the chat card (`PhotoSlot` until then). Real people with permission, Bangladeshi settings; no stock offices.
- Product screenshots go in `ScreenshotFrame`. The hero `ChatDemo` is the one drawn chat, clearly labelled "Example".
- No illustrations, robots, orbs, blobs or icons in circles.

## Motion

- The hero chat switches language every 5 seconds (fade and 6px rise, 350ms) and stops when a visitor picks one.
- The businesses strip slides left to right over 45 seconds and pauses on hover.
- Buttons press down 1px; the FAQ plus turns to a cross. Under reduced motion nothing moves and the strip wraps.

## Accessibility

- Focus ring: 3px solid `ink`, 3px offset. Tap targets at least 44px. Language buttons use `aria-pressed` and `lang`. Frames and photo slots carry `role="img"` and a label.

## Iconography

- Only the moon/sun on the mode toggle and the FAQ plus, inline stroke, 2px, `currentColor`. No emoji.

## Logo

- For now: "halcyo", lowercase, Baloo Da 2 800, `ink`. The three kingfisher proposals in `assets/Logos` are still teal and get redrawn in `ink` with a Marigold detail once one is picked.
