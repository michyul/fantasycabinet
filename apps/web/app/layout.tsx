import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "FantasyCabinet",
  description: "Fantasy politics for Canadian federal and provincial play"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
