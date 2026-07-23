import { Loader2 } from "lucide-react";
import { getTranslations } from "next-intl/server";

export default async function AboutLoading() {
  const t = await getTranslations("common");
  return (
    <main className="flex min-h-screen items-center justify-center bg-background text-muted-foreground">
      <div className="flex items-center gap-2 text-sm" role="status">
        <Loader2 size={16} className="animate-spin" />
        {t("loading")}
      </div>
    </main>
  );
}
