"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useBffHealth } from "@/hooks/use-pipeline";
import {
  LayoutDashboard,
  Layers,
  Search,
  ShieldCheck,
  Radio,
  Settings2,
  MessageSquare,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_ITEMS: {
  href: string;
  label: string;
  icon: LucideIcon;
}[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/events", label: "Events", icon: Layers },
  { href: "/search", label: "Search", icon: Search },
  { href: "/qa", label: "QA Review", icon: ShieldCheck },
  { href: "/feedback", label: "反馈与策略", icon: MessageSquare },
  { href: "/settings", label: "采集配置", icon: Settings2 },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [alertCount, setAlertCount] = useState(0);
  const { data: bffHealth } = useBffHealth();
  const bffDown = bffHealth && !bffHealth.connected;

  useEffect(() => {
    fetch("/api/notifications")
      .then((r) => r.json())
      .then((body) => setAlertCount(Number(body?.total) || 0))
      .catch(() => setAlertCount(0));
  }, [pathname]);

  return (
    <div className="flex min-h-screen">
      <aside className="fixed left-0 top-0 z-40 flex h-screen w-[220px] flex-col border-r border-white/[0.06] bg-[#080809]/90 backdrop-blur-xl">
        <div className="flex items-center gap-2 border-b border-white/[0.06] px-5 py-5">
          <Radio className="h-5 w-5 text-sky-400" />
          <div>
            <p className="text-sm font-semibold tracking-tight text-zinc-100">
              低空经济情报
            </p>
            <p className="text-[10px] uppercase tracking-widest text-zinc-500">
              Event Intelligence
            </p>
          </div>
        </div>
        <nav className="flex flex-1 flex-col gap-1 p-3">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active =
              item.href === "/dashboard"
                ? pathname === "/dashboard" || pathname === "/"
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
      <main className="main-content ml-[220px] flex-1 bg-zinc-50">
        <header className="sticky top-0 z-30 border-b border-zinc-200 bg-white/80 px-8 py-4 backdrop-blur-xl">
          <div className="flex items-center justify-between gap-4">
            <p className="text-xs text-zinc-600">V6 开发 · platform-v6 :3001 → BFF :8788</p>
            <div className="flex flex-wrap items-center gap-2">
              {bffDown ? (
                <span className="rounded-full bg-red-100 px-3 py-1 text-xs font-medium text-red-800">
                  BFF 未连接 · 请在本机终端执行：cd platform-v6 && npm run dev
                </span>
              ) : null}
              {alertCount > 0 ? (
                <Link
                  href="/settings"
                  className="rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-900"
                >
                  {alertCount} 条健康告警
                </Link>
              ) : null}
            </div>
          </div>
        </header>
        <div key={pathname} className="px-8 py-6">
          {children}
        </div>
      </main>
    </div>
  );
}
