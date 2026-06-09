import { cn } from "@/lib/utils";

export function Badge({
  className,
  children,
  variant = "default",
}: {
  className?: string;
  children: React.ReactNode;
  variant?: "default" | "accent" | "muted" | "danger";
}) {
  const variants = {
    default: "bg-zinc-100 text-zinc-700 border-zinc-200",
    accent: "bg-sky-50 text-sky-700 border-sky-200",
    muted: "bg-zinc-100 text-zinc-600 border-zinc-200",
    danger: "bg-rose-50 text-rose-700 border-rose-200",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium",
        variants[variant],
        className,
      )}
    >
      {children}
    </span>
  );
}
