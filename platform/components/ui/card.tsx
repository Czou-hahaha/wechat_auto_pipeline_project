"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export function CardStatic({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className={cn("glass rounded-xl p-4 shadow-lg shadow-black/20", className)}
    >
      {children}
    </motion.div>
  );
}
