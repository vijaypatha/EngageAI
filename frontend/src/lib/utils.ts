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

// ✅ Converts relative timing strings into UTC ISO date strings
export const calculateSendTimeUTC = (timingString: string | undefined): string => {
  const now = new Date();

  const lowerTiming = (timingString || 'immediately').toLowerCase().trim();

  if (lowerTiming === 'immediately') {
    return now.toISOString();
  }

  const match = lowerTiming.match(/^in (\d+)\s+(day|week|month)s?$/);
  if (match) {
    const value = parseInt(match[1], 10);
    const unit = match[2];
    const futureDate = new Date(now);

    try {
      switch (unit) {
        case 'day':
          futureDate.setDate(futureDate.getDate() + value);
          break;
        case 'week':
          futureDate.setDate(futureDate.getDate() + value * 7);
          break;
        case 'month':
          futureDate.setMonth(futureDate.getMonth() + value);
          break;
        default:
          console.warn(`calculateSendTimeUTC: Unrecognized unit '${unit}' in timing: "${timingString}". Defaulting to now.`);
          return now.toISOString();
      }
      if (isNaN(futureDate.getTime())) {
        throw new Error("Date calculation resulted in an invalid date.");
      }
      return futureDate.toISOString();
    } catch (error) {
      console.error(`calculateSendTimeUTC: Error calculating future date for timing "${timingString}":`, error);
      return new Date().toISOString();
    }
  }

  console.warn(`calculateSendTimeUTC: Could not parse timing string: "${timingString}". Defaulting to now.`);
  return now.toISOString();
};