import { Skeleton } from "@/components/ui/skeleton";

export function ChartSkeleton() {
  return (
    <div aria-label="正在准备分析图表" aria-live="polite" className="space-y-5" role="status">
      <div className="flex items-end gap-3">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-5 w-24" />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
      </div>
      <div className="relative h-80 overflow-hidden rounded-2xl border bg-canvas p-6">
        <div className="absolute inset-x-6 bottom-12 flex items-end gap-3">
          {[32, 48, 65, 56, 74, 88, 68, 82, 94].map((height, index) => (
            <Skeleton className="flex-1" key={`${height}-${index}`} style={{ height: `${height}%` }} />
          ))}
        </div>
      </div>
    </div>
  );
}
