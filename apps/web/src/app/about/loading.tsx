import { Loader2 } from "lucide-react";

export default function AboutLoading() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background text-muted-foreground">
      <div className="flex items-center gap-2 text-sm" role="status">
        <Loader2 size={16} className="animate-spin" />
        正在打开
      </div>
    </main>
  );
}
