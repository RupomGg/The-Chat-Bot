import type { Metadata } from "next";
import { Anek_Bangla, Hind_Siliguri } from "next/font/google";
import "./globals.css";

const anek = Anek_Bangla({ subsets: ["bengali", "latin"], weight: ["500", "600", "700"], variable: "--font-anek" });
const hind = Hind_Siliguri({ subsets: ["bengali", "latin"], weight: ["400", "500", "600"], variable: "--font-hind" });

export const metadata: Metadata = {
  metadataBase: new URL("https://halcyo.tech"),
  title: "Halcyo: every customer message answered",
  description:
    "Halcyo replies on Messenger, WhatsApp and your website in Bangla, Banglish or English, and books appointments for you.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${anek.variable} ${hind.variable} antialiased`} suppressHydrationWarning>
      <head>
        {/* Applies a saved dark choice before paint, so there's no flash of light mode. */}
        <script dangerouslySetInnerHTML={{ __html: `try{if(localStorage.getItem("theme")==="dark")document.documentElement.classList.add("dark")}catch(e){}` }} />
      </head>
      <body className="font-sans">{children}</body>
    </html>
  );
}
