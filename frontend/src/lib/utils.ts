import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function getCurrentBusiness(): number | null {
  const businessId = localStorage.getItem('business_id');
  return businessId ? parseInt(businessId, 10) : null;
}