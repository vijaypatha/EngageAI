// frontend/src/lib/utils.ts
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

// Merges Tailwind classes intelligently
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Gets the current business ID from local storage
export const getCurrentBusiness = () => {
  if (typeof window !== "undefined") {
    const stored = localStorage.getItem("business_id");
    return stored ? parseInt(stored) : null;
  }
  return null;
};

// Converts relative timing strings into UTC ISO date strings
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

/**
 * Formats a raw phone number string into a human-readable (XXX) YYY-ZZZZ format.
 * Assumes a +1 country code if not present for US numbers.
 */
export const formatPhoneNumber = (rawPhoneNumber: string | null | undefined): string => {
  if (!rawPhoneNumber) return '';
  const digits = rawPhoneNumber.replace(/\D/g, '');

  if (digits.length === 10) {
    return `(${digits.substring(0, 3)}) ${digits.substring(3, 6)}-${digits.substring(6, 10)}`;
  } else if (digits.length === 11 && digits.startsWith('1')) {
    return `(${digits.substring(1, 4)}) ${digits.substring(4, 7)}-${digits.substring(7, 11)}`;
  } else if (digits.length > 11 && digits.startsWith('1')) {
    return `+${digits}`;
  } else if (digits.length > 10 && !digits.startsWith('1')) {
    return `+${digits}`;
  }
  return rawPhoneNumber.startsWith('+') ? rawPhoneNumber : `+${digits}`;
};

/**
 * Normalizes a phone number to E.164 format (+CountryCodePhoneNumber).
 * Handles common US formats automatically.
 */
export const normalizePhoneNumber = (input: string): string => {
  if (!input) return '';
  let digits = input.replace(/\D/g, '');

  if (digits.length === 10) {
    return `+1${digits}`;
  } else if (digits.length === 11 && digits.startsWith('1')) {
    return `+${digits}`;
  } else if (digits.length > 11 && digits.startsWith('1')) {
    return `+${digits}`;
  } else if (digits.length > 0 && !digits.startsWith('1') && !input.startsWith('+')) {
    return `+1${digits}`;
  }

  if (input.startsWith('+') && digits.length > 0) {
    return `+${digits}`;
  }

  return input;
};