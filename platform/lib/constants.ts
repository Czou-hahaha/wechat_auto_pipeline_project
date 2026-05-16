export const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: "LayoutDashboard" },
  { href: "/events", label: "Events", icon: "Layers" },
  { href: "/search", label: "Search", icon: "Search" },
  { href: "/settings", label: "采集配置", icon: "Settings" },
  { href: "/qa", label: "QA Review", icon: "ShieldCheck" },
] as const;

export const BFF_BASE =
  process.env.BFF_BASE_URL?.replace(/\/$/, "") || "http://127.0.0.1:8787";
