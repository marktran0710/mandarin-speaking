import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "慢慢中文 · Mandarin, little by little",
  description: "A calm Mandarin speaking practice workspace.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
