import type { Metadata } from "next";
import { Legal } from "@/components/Legal";

export const metadata: Metadata = { title: "Privacy Policy · Halcyo" };

export default function Privacy() {
  return (
    <Legal title="Privacy Policy">
      <p>
        Halcyo (&quot;we&quot;) runs an AI assistant that answers customer messages for service businesses in Bangladesh on Facebook
        Messenger, WhatsApp, Telegram and their websites. This policy explains what we collect, why, and your rights under the
        Bangladesh Personal Data Protection Act 2026 (&quot;PDP Act&quot;).
      </p>

      <h2>1. Who this covers</h2>
      <ul>
        <li><b>Visitors to halcyo.tech</b>: people reading this website.</li>
        <li><b>Our clients</b>: businesses that use Halcyo, and their staff who log in.</li>
        <li><b>Customers of our clients</b>: people who chat with a business that uses Halcyo.</li>
      </ul>

      <h2>2. Website visitors</h2>
      <p>
        This website does not use cookies, advertising trackers or analytics that identify you. It stores one setting in your
        browser (light or dark mode). Our hosting providers (Vercel, Cloudflare) keep standard server logs, such as IP address
        and browser type, for security and are not used to profile you. If you message us on WhatsApp or by email, we use what
        you send only to reply.
      </p>

      <h2>3. People chatting with a business that uses Halcyo</h2>
      <p>
        The business you are chatting with decides how your information is used: it is the <b>data controller</b>. We process it
        only on that business&apos;s instructions, as its <b>data processor</b>.
      </p>
      <ul>
        <li><b>What we process:</b> your messages and the replies; what you choose to share, such as your name, phone number, email,
          and details the business needs to help you (for example, the course you want, your pet&apos;s breed, or the day you want an
          appointment); your chat id on the channel you use; which ad brought you, if any; appointments you book.</li>
        <li><b>What we never ask for in chat:</b> passport, national ID, bank or card details, medical reports or case documents.
          If you send card, national ID or passport numbers, the assistant hides them before storing. Please bring documents to
          your appointment instead.</li>
        <li><b>Why:</b> to answer your questions, book appointments, let the business&apos;s staff follow up, and keep the service
          safe and working.</li>
        <li><b>Health and legal matters:</b> the assistant does not give medical or legal advice and does not ask for symptoms,
          diagnoses or case details. Clinics and law firms use it only for booking and general questions about their services.</li>
        <li><b>Under 18:</b> if you are under 18, please ask a parent or guardian to join your appointment.</li>
        <li><b>AI:</b> you are chatting with an automated assistant. You can ask for a person at any time.</li>
      </ul>

      <h2>4. Our clients and their staff</h2>
      <p>
        We collect business contact details, staff names, emails and login data, billing records, and usage data (number of
        conversations, AI usage and costs) to provide the service, invoice, give support and keep accounts secure.
      </p>

      <h2>5. Who helps us run the service (sub-processors)</h2>
      <ul>
        <li>Railway (application hosting) and Neon (database): servers in Singapore.</li>
        <li>Anthropic (Claude) and, if a client chooses it, Google (Gemini): AI models that write replies, in the United States.
          Under their commercial terms, the data is not used to train their models.</li>
        <li>Meta (Messenger, WhatsApp) and Telegram: the channels messages travel through.</li>
        <li>Resend: email notifications to staff. Vercel and Cloudflare: this website and network security.</li>
      </ul>
      <p>
        Because some of these providers are outside Bangladesh, your information may be processed abroad. Each provider handles
        it under its own privacy and security terms, only to provide its part of the service.
      </p>

      <h2>6. How long we keep it</h2>
      <ul>
        <li>Chat messages: deleted after 12 months, or sooner if the business chooses.</li>
        <li>Contact details: until the business deletes them or you ask for deletion.</li>
        <li>Usage records without message text: kept for billing and accounting.</li>
      </ul>

      <h2>7. Security</h2>
      <p>
        Data is encrypted in transit (HTTPS). Channel access tokens and secrets are encrypted at rest. Each client&apos;s data is kept
        separate, staff access is limited by role, and we keep backups and test restoring them.
      </p>

      <h2>8. Your rights</h2>
      <p>
        You can ask to see, correct or delete your information, or to stop its use. If you chatted with a business, write
        &quot;delete my data&quot; in the same chat or contact the business; we help them act on it. You can also email{" "}
        <a href="mailto:contact@halcyo.tech">contact@halcyo.tech</a>. We reply within 30 days.
      </p>

      <h2>9. We don&apos;t sell data</h2>
      <p>We never sell personal information or use it for advertising.</p>

      <h2>10. Changes</h2>
      <p>We will update this page when our practices change and show the new date at the top.</p>
    </Legal>
  );
}
