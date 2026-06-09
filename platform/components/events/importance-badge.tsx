import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function ImportanceBadge({ score }: { score: number }) {
  const variant =
    score >= 90 ? "accent" : score >= 75 ? "default" : "muted";
  return (
    <Badge variant={variant} className={cn("tabular-nums")}>
      IMP {score}
    </Badge>
  );
}
