import { Suspense } from "react";
import { CasePage } from "@/components/CasePage";

export default function Page({ params }: { params: Promise<{ id: string }> }) {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-zinc-500">Opening case…</div>}>
      {params.then(({ id }) => (
        <CasePage id={decodeURIComponent(id)} />
      ))}
    </Suspense>
  );
}
