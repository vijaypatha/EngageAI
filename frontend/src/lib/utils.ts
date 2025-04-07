import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// ✅ Gets business info from session cookie
export async function getCurrentBusiness() {
  try {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_BASE}/auth/me`, {
      credentials: "include",
    });

    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.error("Error fetching current business:", err);
    return null;
  }
}