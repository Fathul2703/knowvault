import type { Metadata } from "next";
import { connection } from "next/server";
import type { ReactNode } from "react";

import { Providers } from "./providers";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "KnowVault", template: "%s · KnowVault" },
  description: "Personal knowledge management with grounded, cited AI answers.",
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  // Every page is rendered per request, so its scripts carry that request's CSP nonce
  // (src/proxy.ts). Prerendered pages would have no nonce and be blocked.
  await connection();
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
