// 📄 File: frontend/src/lib/utils.ts

import { ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

// ✅ Merges Tailwind classes intelligently
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// lib/utils.ts
export const getCurrentBusiness = () => {
  if (typeof window !== "undefined") {
    const stored = localStorage.getItem("business_id");
    return stored ? parseInt(stored) : null;
  }
  return null;
};