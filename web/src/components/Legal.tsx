import Link from "next/link";

export const UPDATED = "10 October 2026";

// Shared frame for the legal pages: back link, title, date, readable prose.
export function Legal({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <main className="mx-auto max-w-3xl px-5 py-12 md:px-8">
      <Link href="/" className="font-display text-xl font-bold">halcyo</Link>
      <h1 className="mt-10 font-display text-4xl font-bold">{title}</h1>
      <p className="mt-2 text-sm text-soft">Last updated {UPDATED}</p>
      <div className="mt-8 grid gap-4 leading-relaxed [&_a]:text-brand [&_a]:underline [&_h2]:mt-6 [&_h2]:font-display [&_h2]:text-2xl [&_h2]:font-semibold [&_li]:ml-5 [&_li]:list-disc [&_ul]:grid [&_ul]:gap-1.5">
        {children}
      </div>
      <p className="mt-12 border-t border-line pt-6 text-sm text-soft">
        Questions about this page: <a href="mailto:contact@halcyo.tech" className="text-brand underline">contact@halcyo.tech</a>.
        See also our <Link href="/privacy" className="underline">Privacy Policy</Link>, <Link href="/terms" className="underline">Terms of Service</Link> and{" "}
        <Link href="/data-processing" className="underline">Data Processing Terms</Link>.
      </p>
    </main>
  );
}
