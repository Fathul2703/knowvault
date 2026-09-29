import type { Metadata } from "next";

import { LibraryPage } from "@/features/library/library-page";

export const metadata: Metadata = { title: "Library" };

export default function Page() {
  return <LibraryPage />;
}
