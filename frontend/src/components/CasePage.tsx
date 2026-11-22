"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useCases, useOverview } from "@/lib/api";
import { editionNames } from "@/lib/derive";
import { CaseDetailView } from "./CaseDetail";
import { Header } from "./Header";
import { btn, Card, Icon } from "./ui";

export function CasePage({ id }: { id: string }) {
  const { data: ov } = useOverview();
  useCases(); // keep the queue warm for the way back
  const names = useMemo(() => editionNames(ov), [ov]);
  return (
    <div className="min-h-screen">
      <Header ov={ov} />
      <main className="mx-auto max-w-[1240px] px-5 pb-16 pt-4">
        <Link href="/" className={btn.quiet}>
          <Icon name="arrow" className="h-3.5 w-3.5 rotate-180" />
          <span className="text-[13px]">Launch room</span>
        </Link>
        <Card className="mt-3 pb-6">
          <CaseDetailView id={id} names={names} layout="page" />
        </Card>
      </main>
    </div>
  );
}
