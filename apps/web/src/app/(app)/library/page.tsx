import type { Metadata } from "next";

import { LibraryView } from "@/features/library/library-view";

export const metadata: Metadata = { title: "Library" };

export default function LibraryPage() {
  // Documents are not stored yet (Phase 2), so the library is always empty for now.
  return <LibraryView items={[]} />;
}
