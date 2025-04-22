import { formatInTimeZone, toZonedTime } from 'date-fns-tz';
import { format as dateFnsFormat } from 'date-fns';

// US Timezones only
export const US_TIMEZONES = [
  'America/New_York',      // Eastern
  'America/Chicago',       // Central
  'America/Denver',        // Mountain
  'America/Phoenix',       // Arizona
  'America/Los_Angeles',   // Pacific
  'America/Anchorage',     // Alaska
  'Pacific/Honolulu',      // Hawaii
];

export const TIMEZONE_LABELS: { [key: string]: string } = {
  'America/New_York': 'Eastern Time',
  'America/Chicago': 'Central Time',
  'America/Denver': 'Mountain Time',
  'America/Phoenix': 'Arizona Time',
  'America/Los_Angeles': 'Pacific Time',
  'America/Anchorage': 'Alaska Time',
  'Pacific/Honolulu': 'Hawaii Time',
};

// Get the user's timezone, ensuring it's a US timezone
export function getUserTimezone(): string {
  const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  return US_TIMEZONES.includes(browserTz) ? browserTz : 'America/New_York';
}

// Format a date in a specific timezone with an optional format
export function formatInUserTimezone(date: Date | string, timezone: string, format: string = 'MMM d, yyyy h:mm a'): string {
  const dateObj = typeof date === 'string' ? new Date(date) : date;
  return formatInTimeZone(dateObj, timezone, format);
}

// Get timezone abbreviation (ET, CT, etc.)
export function getTimezoneAbbr(timezone: string): string {
  const date = new Date();
  return new Intl.DateTimeFormat('en-US', {
    timeZone: timezone,
    timeZoneName: 'short',
  })
    .formatToParts(date)
    .find(part => part.type === 'timeZoneName')?.value || '';
}

// Convert time between timezones
export function convertTime(time: string, fromTimezone: string, toTimezone: string): Date {
  const date = new Date(time);
  const fromOffset = getTimezoneOffset(fromTimezone, date);
  const toOffset = getTimezoneOffset(toTimezone, date);
  const diffMinutes = toOffset - fromOffset;
  return new Date(date.getTime() + diffMinutes * 60 * 1000);
}

// Get timezone offset in minutes for a specific date
function getTimezoneOffset(timezone: string, date: Date): number {
  const utcDate = new Date(date.toLocaleString('en-US', { timeZone: 'UTC' }));
  const tzDate = new Date(date.toLocaleString('en-US', { timeZone: timezone }));
  return (utcDate.getTime() - tzDate.getTime()) / (60 * 1000);
}

// Format a date in a specific timezone
export function formatToUserTimezone(date: Date | string | number, formatStr: string, timezone?: string): string {
    const userTimezone = timezone || getUserTimezone();
    return formatInTimeZone(date, userTimezone, formatStr);
}

// Convert a date to a specific timezone
export function formatToLocalTime(date: Date | string | number, timezone?: string): string {
    const userTimezone = timezone || getUserTimezone();
    const zonedDate = toZonedTime(date, userTimezone);
    return dateFnsFormat(zonedDate, 'h:mm a');
}

// Format a date with timezone information
export function formatToLocalDate(date: Date | string | number, timezone?: string): string {
    const userTimezone = timezone || getUserTimezone();
    const zonedDate = toZonedTime(date, userTimezone);
    return dateFnsFormat(zonedDate, 'MMM d, yyyy');
}

// Format a date with timezone information
export function formatToLocalDateTime(date: Date | string | number, timezone?: string): string {
    const userTimezone = timezone || getUserTimezone();
    const zonedDate = toZonedTime(date, userTimezone);
    return dateFnsFormat(zonedDate, 'MMM d, yyyy h:mm a');
}

// Format a date with timezone information
export function formatWithTimezoneInfo(
    date: Date | string,
    timezone: string,
    formatStr: string = 'MMM d, yyyy h:mm a'
): string {
    const formattedDate = formatToUserTimezone(date, formatStr);
    const timezoneAbbr = getTimezoneAbbr(timezone);
    return `${formattedDate} (${timezoneAbbr})`;
}

// Format a date range in a specific timezone
export function formatDateRange(
    startDate: Date | string,
    endDate: Date | string,
    timezone: string,
    formatStr: string = 'MMM d, yyyy h:mm a'
): string {
    const start = formatToUserTimezone(startDate, formatStr);
    const end = formatToUserTimezone(endDate, formatStr);
    return `${start} - ${end}`;
}

// Check if a date is within business hours (9 AM - 5 PM)
export function isBusinessHours(date: Date | string, timezone: string): boolean {
    const localDate = toZonedTime(date, timezone);
    const hour = localDate.getHours();
    const isWeekday = localDate.getDay() >= 1 && localDate.getDay() <= 5;
    return isWeekday && hour >= 9 && hour < 17;
}

// Get the next business hour for a given date
export function getNextBusinessHour(date: Date | string, timezone: string): Date {
    let localDate = toZonedTime(date, timezone);
    
    // If it's a weekend, move to next Monday
    if (localDate.getDay() >= 6) {
        const daysUntilMonday = 8 - localDate.getDay();
        localDate = new Date(localDate);
        localDate.setDate(localDate.getDate() + daysUntilMonday);
        localDate.setHours(9, 0, 0, 0);
        return localDate;
    }
    
    // If it's before business hours, move to start of business hours
    if (localDate.getHours() < 9) {
        localDate = new Date(localDate);
        localDate.setHours(9, 0, 0, 0);
        return localDate;
    }
    
    // If it's after business hours, move to next day's start of business hours
    if (localDate.getHours() >= 17) {
        localDate = new Date(localDate);
        localDate.setDate(localDate.getDate() + 1);
        localDate.setHours(9, 0, 0, 0);
        return localDate;
    }
    
    return localDate;
}

// Format a date for display in both business and customer timezones
export function formatDualTimezone(
    date: Date | string,
    businessTimezone: string,
    customerTimezone?: string
): { businessTime: string; customerTime?: string } {
    const result: { businessTime: string; customerTime?: string } = {
        businessTime: formatWithTimezoneInfo(date, businessTimezone)
    };
    
    if (customerTimezone) {
        result.customerTime = formatWithTimezoneInfo(date, customerTimezone);
    }
    
    return result;
}

// Debug utility for logging timezone information
export function logTimezoneInfo(
    date: Date | string,
    timezone: string,
    label: string = 'Date'
): void {
    console.log(`[${label}]`);
    console.log('UTC:', new Date(date).toISOString());
    console.log('Local:', formatToUserTimezone(date, 'MMM d, yyyy h:mm a'));
    console.log('Timezone:', timezone);
    console.log('Abbreviation:', getTimezoneAbbr(timezone));
} 