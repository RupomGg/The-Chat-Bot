---
name: Halcyon Cobalt
colors:
  surface: '#f9f9ff'
  surface-dim: '#d9d9e0'
  surface-bright: '#f9f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f3f3fa'
  surface-container: '#ededf4'
  surface-container-high: '#e8e7ef'
  surface-container-highest: '#e2e2e9'
  on-surface: '#1a1b21'
  on-surface-variant: '#434654'
  inverse-surface: '#2e3036'
  inverse-on-surface: '#f0f0f7'
  outline: '#747686'
  outline-variant: '#c4c5d7'
  surface-tint: '#2352d5'
  primary: '#003ab4'
  on-primary: '#ffffff'
  primary-container: '#2453d6'
  on-primary-container: '#d0d8ff'
  inverse-primary: '#b6c4ff'
  secondary: '#885200'
  on-secondary: '#ffffff'
  secondary-container: '#fdaa41'
  on-secondary-container: '#6d4100'
  tertiary: '#802b00'
  on-tertiary: '#ffffff'
  tertiary-container: '#a73b00'
  on-tertiary-container: '#ffcfbd'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dce1ff'
  primary-fixed-dim: '#b6c4ff'
  on-primary-fixed: '#001550'
  on-primary-fixed-variant: '#003ab2'
  secondary-fixed: '#ffddbb'
  secondary-fixed-dim: '#ffb867'
  on-secondary-fixed: '#2b1700'
  on-secondary-fixed-variant: '#673d00'
  tertiary-fixed: '#ffdbce'
  tertiary-fixed-dim: '#ffb599'
  on-tertiary-fixed: '#370e00'
  on-tertiary-fixed-variant: '#7f2b00'
  background: '#f9f9ff'
  on-background: '#1a1b21'
  surface-variant: '#e2e2e9'
typography:
  display-xl:
    fontFamily: Anek Bangla
    fontSize: 56px
    fontWeight: '700'
    lineHeight: 64px
    letterSpacing: -0.02em
  display-xl-mobile:
    fontFamily: Anek Bangla
    fontSize: 38px
    fontWeight: '700'
    lineHeight: 44px
    letterSpacing: -0.01em
  headline-lg:
    fontFamily: Anek Bangla
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
    letterSpacing: -0.015em
  headline-lg-mobile:
    fontFamily: Anek Bangla
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Anek Bangla
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
    letterSpacing: -0.01em
  headline-md-mobile:
    fontFamily: Anek Bangla
    fontSize: 22px
    fontWeight: '600'
    lineHeight: 30px
    letterSpacing: 0em
  headline-sm:
    fontFamily: Anek Bangla
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-lg:
    fontFamily: Hind Siliguri
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Hind Siliguri
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Hind Siliguri
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-lg:
    fontFamily: Hind Siliguri
    fontSize: 15px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: 0.01em
  label-md:
    fontFamily: Hind Siliguri
    fontSize: 13px
    fontWeight: '600'
    lineHeight: 18px
    letterSpacing: 0.02em
  label-sm:
    fontFamily: Hind Siliguri
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.03em
rounded:
  sm: 0.5rem
  DEFAULT: 1rem
  md: 1.5rem
  lg: 2rem
  xl: 3rem
  full: 9999px
spacing:
  gutter: 1.5rem
  margin: 1.25rem
  gutter-desktop: 2rem
  margin-desktop: 5rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2.5rem
---

## Brand & Style

This design system is engineered specifically for transactional service enterprises operating within Bangladesh's conversational commerce ecosystem. The visual execution blends high-clarity transactional rigor with tactile local accessibility, tailored directly for businesses converting leads through WhatsApp, Facebook Messenger, and direct client bookings.

The aesthetic follows an elevated Modern Corporate direction with deliberate soft-brutalist utility:
- **Atmosphere:** Calm, grounded, authoritative, and frictionless.
- **Visual Stance:** Zero decorative gradients, zero AI-generated visual clutter, and strict avoidance of synthetic purple or indigo accents. Every element communicates structural reliability and immediate business legibility.
- **Cultural Adaptability:** Built ground-up for dual-script harmony across Bengali and English typography, maintaining visual weight and metric alignment across bilingual landing pages and conversational touchpoints.

## Colors

The palette establishes an unmistakable hierarchy built on high-contrast operational cobalt, warm architectural neutrals, and deliberate contextual indicators.

### Palette Architecture
- **Brand Primary (`#2453D6`):** Deep Cobalt. Applied exclusively to primary CTAs, active operational indicators, and core conversion paths. Text on Cobalt surfaces must always be Pure White (`#FFFFFF`).
- **Highlight Accent (`#F6A43C`):** Marigold. Strictly reserved for status badges such as "Booked", "Hot Lead", and high-intent transaction triggers. Never use Marigold for raw text on white or light backgrounds to guarantee WCAG compliance; use it as a solid container fill with Ink (`#16181D`) text or alongside its contextual wash.
- **Ink Primary (`#16181D`):** High-density neutral for display typography, lead headlines, and core data readouts.
- **Secondary Ink (`#4B5060`):** Balanced graphite slate for descriptive subtitles, body paragraphs, and supporting metadata.
- **Page Foundation (`#F7F7F5`):** Bone/Off-white canvas providing warm contrast against card modules.
- **Surface Elevation (`#FFFFFF`):** Crisp white reserved for raised operational cards, floating bars, and interactive modals.
- **Wash Containers:**
  - **Cobalt Wash (`#EAF0FF`):** Inbound message bubbles, verified customer badges, and interactive active-state containers.
  - **Sun Wash (`#FDF0DC`):** Background tint for pending actions, highlight badges, and promotional card accents.
- **Structural Lines (`#E3E3DF`):** Low-contrast structural borders defining surface separation without visual visual heaviness.

## Typography

The type system pairs structural display power with effortless readability in both Bangla and Latin scripts.

- **Headline Hierarchy (Anek Bangla):** Serves display titles, value propositions, and section headers. Its condensed structural proportions allow high information density without sacrificing punch. Display titles must maintain tight leading to avoid visual fragmentation when rendering conjunct Bengali characters (*juktakkhor*).
- **Body and Interface Hierarchy (Hind Siliguri):** Powers all narrative body text, metadata, form fields, and operational UI labels. It delivers open counters and uniform stroke weights that remain crisp on low-DPI Android screens and high-resolution mobile viewports alike.
- **Rendering Rules:** Text color assignments are absolute: `#16181D` for headings, `#4B5060` for running copy, and `#FFFFFF` strictly when placed against Cobalt containers. No gradient text masks are permitted.

## Layout & Spacing

The layout is built on a responsive 12-column grid system designed around mobile-first utility, accommodating conversational flows and rapid scan paths.

### Layout Mechanics
- **Mobile (< 768px):** 4-column fluid layout with `1.25rem` outer canvas padding and `1rem` column gutters. Components stack into single-column vertical cards to prioritize thumb-driven taps.
- **Tablet (768px to 1024px):** 8-column layout with `2rem` outer padding and `1.5rem` gutters.
- **Desktop (> 1024px):** 12-column layout capped at an absolute max-width of `1200px` centered within a `margin-desktop` of `5rem` to avoid over-extended horizontal reading lines.

### Spacing Rhythm
- **Micro Space (`space-xs` = 4px, `space-sm` = 8px):** Internal icon-to-label gaps, badge paddings, and inline chip margins.
- **Form & Content Rhythm (`space-md` = 16px, `space-lg` = 24px):** Card internal padding, conversational bubble spacing, and form input stacks.
- **Structural Rhythm (`space-xl` = 40px):** Vertical spacing between distinct landing page sections, content blocks, and operational dashboards.

## Elevation & Depth

Visual hierarchy relies on crisp surface boundary definitions coupled with targeted chromatic depth rather than heavy, muddy drop shadows.

### Elevation Levels
- **Level 0 (Flat Surface):** Page background `#F7F7F5`. Seamless canvas.
- **Level 1 (Card & Module Foundation):** Pure white `#FFFFFF` surface resting on a structural hairline border: `1px solid #E3E3DF` supported by ambient base shadow `0 1px 2px rgb(22 24 29 / 0.04)`.
- **Level 2 (Interactive Floating Elements & Chat Triggers):** Retains the crisp hairline boundary but introduces tinted spatial diffusion: `0 12px 32px rgb(36 83 214 / 0.10)`. Used for WhatsApp launch modules, sticky lead-capture bars, and hovered service tiers.
- **Level 3 (Modals and Dropdowns):** Combination elevation `0 20px 40px rgb(22 24 29 / 0.08)` paired with ambient Cobalt ground tint `0 4px 12px rgb(36 83 214 / 0.06)`.

## Shapes

The shape vocabulary uses a deliberate contrast between full-radius interactive controls and structured architectural card boundaries.

- **Full Pill (`border-radius: 9999px`):** Applied exclusively to all buttons, navigation pills, status badges, chips, category tabs, and floating quick-action triggers. This ensures immediate touch affordance and tactile friendliness.
- **Architectural Cards (`border-radius: 20px`):** Applied systematically to all structural cards, media containers, hero product frames, form shells, and chat interface windows.
- **Chat Bubbles:**
  - Client / Inbound bubbles: `20px` corner radius with bottom-left corner tightened to `6px`.
  - Service / Outbound bubbles: `20px` corner radius with bottom-right corner tightened to `6px`.

## Components

All icons throughout the interface are regular weight icons from the Phosphor icon family, set to match the corresponding text color at 20px or 24px bounding sizes.

### Buttons
- **Primary Action (Brand):** Background `#2453D6`, text `#FFFFFF`, border none, shape full pill (`rounded-full`), vertical padding `14px`, horizontal padding `28px`. Hover state darkens primary to `#1C44B5`.
- **Secondary Action:** Background `#FFFFFF`, text `#16181D`, border `1px solid #E3E3DF`, shape full pill. Hover state shifts background to `#F7F7F5`.
- **Channel Actions (WhatsApp / Messenger):** Full pill button, background `#2453D6` or solid Ink `#16181D`, accompanied by Phosphor WhatsApp or Messenger icons in pure white.

### Badges & Chips
- **Status Badges ("Booked", "Hot lead"):** Background `#F6A43C` with text `#16181D` (Font: Hind Siliguri Bold, 11px uppercase), shape full pill, horizontal padding `10px`, vertical padding `4px`. Alternatively, sun wash container `#FDF0DC` with `#16181D` text and a solid `#F6A43C` indicator dot.
- **Filter Chips:** Full pill container with background `#FFFFFF`, border `1px solid #E3E3DF`, text `#4B5060`. Active chip shifts to background `#EAF0FF`, border `#2453D6`, text `#2453D6`.

### Cards & Service Panels
- **Structure:** Surface `#FFFFFF`, border `1px solid #E3E3DF`, border radius `20px`, internal padding `24px` (`32px` on desktop). Shadow: `0 1px 2px rgb(22 24 29 / 0.04)`.
- **Hover State:** Lifted with shadow `0 12px 32px rgb(36 83 214 / 0.10)` and border color shifts to `#2453D6`.

### Form Fields & Inputs
- **Base Input:** Background `#FFFFFF`, border `1px solid #E3E3DF`, border radius `9999px` for single-line search/phone fields, or `16px` for multi-line request boxes. Height `48px` minimum to accommodate high-frequency mobile input.
- **Focus State:** Border color `#2453D6`, soft outline glow `0 0 0 3px rgb(36 83 214 / 0.15)`. Text `#16181D`, placeholder text `#4B5060`.

### Conversational Preview Widgets
- **Bot / Automated Response Bubble:** Background `#EAF0FF`, text `#16181D`, border radius `20px` (`6px` bottom-left), padding `16px`.
- **Customer Response Bubble:** Background `#FFFFFF`, border `1px solid #E3E3DF`, text `#16181D`, border radius `20px` (`6px` bottom-right), padding `16px`.