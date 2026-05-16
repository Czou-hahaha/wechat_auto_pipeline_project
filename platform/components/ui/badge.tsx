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
    default: "bg-white/5 text-zinc-300 border-white/10",
    accent: "bg-sky-500/10 text-sky-300 border-sky-500/20",
    muted: "bg-zinc-800/50 text-zinc-400 border-zinc-700/50",
    danger: "bg-rose-500/10 text-rose-300 border-rose-500/20",
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
