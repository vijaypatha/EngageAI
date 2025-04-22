declare module 'date-fns-tz' {
    import { format } from 'date-fns';

    export function formatInTimeZone(
        date: Date | string | number,
        timeZone: string,
        formatStr: string
    ): string;

    export function toZonedTime(
        date: Date | string | number,
        timeZone: string
    ): Date;

    export function getTimezoneOffset(timeZone: string, date?: Date): number;
} 