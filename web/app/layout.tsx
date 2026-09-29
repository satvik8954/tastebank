import type { Metadata } from "next";
import { Instrument_Serif, Inter_Tight } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const interTight = Inter_Tight({ variable: "--font-inter-tight", subsets: ["latin"] });
const instrumentSerif = Instrument_Serif({
  variable: "--font-instrument-serif",
  subsets: ["latin"],
  weight: "400",
  style: ["normal", "italic"],
});

export const metadata: Metadata = {
  title: "Round Zero",
  description: "Catch the client's feedback before the client gives it.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${interTight.variable} ${instrumentSerif.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        <header className="border-b border-line bg-card sticky top-0 z-20">
          <div className="mx-auto max-w-[1400px] px-6 h-14 flex items-center gap-8">
            <Link href="/" className="flex items-baseline gap-2">
              <span className="font-serif text-2xl leading-none">Round Zero</span>
              <span className="text-xs text-muted hidden sm:inline">catch the feedback before the client gives it</span>
            </Link>
            <nav className="flex gap-5 text-sm text-muted">
              <Link href="/" className="hover:text-ink">Review</Link>
              <Link href="/clients/dewpoint" className="hover:text-ink">Clients</Link>
            </nav>
            <span className="ml-auto text-xs text-muted">
              memory by <span className="text-memory font-medium">Hindsight</span>
            </span>
          </div>
        </header>
        <main className="flex-1">{children}</main>
      </body>
    </html>
  );
}
