"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import {
  LayoutDashboard,
  Layers,
  Search,
  ShieldCheck,
  Radio,
  Settings2,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_ITEMS: {
  href: string;
  label: string;
  icon: LucideIcon;
}[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/events", label: "Events", icon: Layers },
  { href: "/search", label: "Search", icon: Search },
  { href: "/qa", label: "QA Review", icon: ShieldCheck },
  { href: "/settings", label: "采集配置", icon: Settings2 },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex min-h-screen">
      <aside className="fixed left-0 top-0 z-40 flex h-screen w-[220px] flex-col border-r border-white/[0.06] bg-[#080809]/90 backdrop-blur-xl">
        <motion.div
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          className="flex items-center gap-2 border-b border-white/[0.06] px-5 py-5"
        >
          <Radio className="h-5 w-5 text-sky-400" />
          <div>
            <p className="text-sm font-semibold tracking-tight text-zinc-100">
              低空经济情报
            </p>
            <p className="text-[10px] uppercase tracking-widest text-zinc-500">
              Event Intelligence
            </p>
          </div>
        </motion.div>
        <nav className="flex flex-1 flex-col gap-1 p-3">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors",
                  active
                    ? "bg-white/[0.08] text-zinc-100"
                    : "text-zinc-500 hover:bg-white/[0.04] hover:text-zinc-300",
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-white/[0.06] p-4 text-[11px] text-zinc-600">
          AI Intelligence Platform
        </div>
      </aside>
      <main className="ml-[220px] flex-1">
        <header className="sticky top-0 z-30 border-b border-white/[0.06] bg-[#0a0a0b]/80 px-8 py-4 backdrop-blur-xl">
          <p className="text-xs text-zinc-500">实时事件情报 · 以 Event 为核心</p>
        </header>
        <motion.div
          key={pathname}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          className="px-8 py-6"
        >
          {children}
        </motion.div>
      </main>
    </div>
  );
}
