import type { Metadata } from "next";
import Link from "next/link";
import { Legal } from "@/components/Legal";

export const metadata: Metadata = { title: "Data Processing Terms · Halcyo" };

export default function DataProcessing() {
  return (
    <Legal title="Data Processing Terms">
      <p>
        These terms are part of our <Link href="/terms">Terms of Service</Link>. They cover the personal data of your customers that
        Halcyo processes for you, under the Bangladesh Personal Data Protection Act 2026.
      </p>

      <h2>1. Roles</h2>
      <p>You are the data controller. Halcyo is your data processor and acts only on your documented instructions.</p>

      <h2>2. What we process and why</h2>
      <ul>
        <li><b>People:</b> your customers and prospects who message you, and your staff users.</li>
        <li><b>Data:</b> messages, contact details, the profile fields you choose (for example study plans, pet details or
          preferred appointment time), appointments and source ad.</li>
        <li><b>Purpose:</b> answering questions, booking, notifying your staff, reporting and support.</li>
        <li><b>Not processed:</b> national ID, passport, bank or card numbers (masked if sent), medical records, legal case files.</li>
      </ul>

      <h2>3. Your obligations</h2>
      <ul>
        <li>Have a lawful basis and a privacy notice for your customers that mentions Halcyo; the assistant shows a short notice
          and a link in its first message.</li>
        <li>For customers under 18, follow the PDP Act rules on parental consent.</li>
        <li>Give us accurate instructions and knowledge.</li>
      </ul>

      <h2>4. Our obligations</h2>
      <ul>
        <li>Process data only to provide the service and keep it confidential.</li>
        <li>Limit staff access to people who need it for support or maintenance.</li>
        <li>Encrypt data in transit and secrets at rest, keep each client&apos;s data separate, back it up and test restores.</li>
        <li>Tell you without undue delay, and within 72 hours, after we become aware of a personal data breach affecting your data.</li>
        <li>Help you answer requests from your customers to access, correct or delete their data.</li>
      </ul>

      <h2>5. Sub-processors</h2>
      <p>
        We use the providers listed in our <Link href="/privacy">Privacy Policy</Link> (hosting in Singapore, AI models in the United
        States, Meta and Telegram for channels, email delivery). We will tell you at least 30 days before adding a new one, and
        you may object.
      </p>

      <h2>6. Transfers abroad</h2>
      <p>Some processing happens outside Bangladesh, with providers bound by their own security and confidentiality terms.</p>

      <h2>7. Retention and deletion</h2>
      <p>
        Messages are deleted after 12 months unless you set a shorter period. When the service ends you can export everything;
        we then delete your data within 30 days, except records the law requires us to keep.
      </p>

      <h2>8. Audits</h2>
      <p>On reasonable written request, once a year, we will answer your security questions and share how we protect your data.</p>

      <h2>9. Signed version</h2>
      <p>
        If you need a signed data processing agreement, email <a href="mailto:contact@halcyo.tech">contact@halcyo.tech</a>.
      </p>
    </Legal>
  );
}
