import { Skeleton } from "@/components/ui/skeleton";

export function EventDetailSkeleton() {
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <Skeleton className="h-5 w-24" />
      <Skeleton className="h-10 w-3/4" />
      <Skeleton className="h-28 w-full" />
      <Skeleton className="h-[min(58vh,560px)] w-full" />
      <Skeleton className="h-10 w-64" />
    </div>
  );
}
