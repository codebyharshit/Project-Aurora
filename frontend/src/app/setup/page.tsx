import type { Metadata } from "next";
import { SetupPage } from "@/components/SetupPage";

export const metadata: Metadata = { title: "How Aurora is set up for Soony · Aurora" };

export default function Page() {
  return <SetupPage />;
}
