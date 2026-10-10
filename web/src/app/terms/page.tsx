import type { Metadata } from "next";
import Link from "next/link";
import { Legal } from "@/components/Legal";

export const metadata: Metadata = { title: "Terms of Service · Halcyo" };

export default function Terms() {
  return (
    <Legal title="Terms of Service">
      <p>
        These terms apply between Halcyo, operated from Dhaka, Bangladesh (&quot;we&quot;), and the business that signs up for
        Halcyo (&quot;you&quot;). By using the service you agree to them. A signed order form or proposal takes priority over these
        terms where they differ.
      </p>

      <h2>1. The service</h2>
      <p>
        Halcyo is an AI assistant that answers your customers on Messenger, WhatsApp, Telegram and your website, collects their
        details, books appointments and alerts your staff. We set it up for you (&quot;done for you&quot;), using the information you
        give us about your business.
      </p>

      <h2>2. AI answers and your responsibility</h2>
      <ul>
        <li>The assistant answers only from the knowledge you approve. You are responsible for keeping fees, timings, policies
          and other facts accurate and for telling us about changes.</li>
        <li>AI can make mistakes. We test before going live and route unknown questions to your staff, but we don&apos;t guarantee
          every answer is correct.</li>
        <li>The assistant does <b>not</b> give medical, legal, immigration or financial advice, and it never guarantees outcomes
          such as visas, admissions, diagnoses or case results. You must not ask us to configure it to do so.</li>
      </ul>

      <h2>3. Acceptable use</h2>
      <p>You agree not to use Halcyo to:</p>
      <ul>
        <li>send spam, unsolicited marketing, or messages outside the rules of Meta, WhatsApp or Telegram;</li>
        <li>make false or misleading claims, or help anyone falsify documents;</li>
        <li>collect sensitive data the service is not designed for (national ID, passport, bank, card or medical records);</li>
        <li>break any law, including the Bangladesh Personal Data Protection Act 2026.</li>
      </ul>
      <p>We may pause the service if it is being used this way, and will tell you why.</p>

      <h2>4. Your accounts and channels</h2>
      <p>
        Your Facebook Page, WhatsApp Business account and other channels stay yours. You give us the access needed to connect
        and run them. WhatsApp message fees are billed by Meta directly to you.
      </p>

      <h2>5. Plans, payment and cancellation</h2>
      <ul>
        <li>Plans are billed monthly in advance, in Bangladeshi taka, by bank transfer or bKash. A one-time setup fee covers
          writing your knowledge, connecting channels and training your staff.</li>
        <li>Each plan includes a monthly number of conversations. Extra conversations are billed at the rate in your order form.
          If you reach the hard limit, the assistant tells customers a staff member will reply.</li>
        <li>Invoices are due within 7 days. If payment is more than 15 days late, we may pause the service after notice.</li>
        <li>You can cancel at any time with 30 days&apos; written notice. Monthly fees already paid are not refunded for the
          remaining days.</li>
        <li>The setup fee is refunded in full if we cannot make your service live within 15 working days of receiving everything
          we asked for. Once you are live, it is not refundable.</li>
        <li>Pilot offers (discounts or a waived setup fee) apply only as stated in writing.</li>
      </ul>

      <h2>6. Data</h2>
      <p>
        You own your data and your customers&apos; data. We process it only to provide the service, as described in our{" "}
        <Link href="/data-processing">Data Processing Terms</Link> and <Link href="/privacy">Privacy Policy</Link>. When you leave, you can
        export your data, and we delete it within 30 days unless the law requires us to keep it.
      </p>

      <h2>7. Availability and support</h2>
      <p>
        We aim for 99.5% monthly uptime and monitor the service around the clock. Support is by WhatsApp and email during
        business hours (Saturday to Thursday, 10:00 to 19:00, Dhaka time). Planned maintenance is announced in advance.
      </p>

      <h2>8. Intellectual property</h2>
      <p>
        The Halcyo software, design and brand belong to us. Your content, logos and knowledge belong to you; you let us use
        them only to run your service.
      </p>

      <h2>9. Liability</h2>
      <p>
        To the extent the law allows, we are not liable for indirect losses such as lost profits or lost customers, and our
        total liability in any 12 months is limited to the fees you paid us in that period. Nothing here limits liability that
        cannot be limited by law.
      </p>

      <h2>10. Ending the service</h2>
      <p>
        Either side may end the service with 30 days&apos; written notice, or immediately if the other side seriously breaks these
        terms and does not fix it within 15 days of notice.
      </p>

      <h2>11. Changes</h2>
      <p>We may update these terms. We will tell clients about important changes at least 30 days before they apply.</p>

      <h2>12. Law</h2>
      <p>These terms are governed by the laws of Bangladesh. The courts of Dhaka have jurisdiction.</p>
    </Legal>
  );
}
