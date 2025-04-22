import React, { useState, useEffect } from 'react';
import { format, parse } from 'date-fns';
import { useTimezone } from '@/hooks/useTimezone';
import { 
    formatInUserTimezone, 
    convertTime, 
    isBusinessHours, 
    getNextBusinessHour,
    TIMEZONE_LABELS 
} from '@/lib/timezone';

interface TimezoneDatePickerProps {
    value: Date | null;
    onChange: (date: Date | null) => void;
    label?: string;
    minDate?: Date;
    maxDate?: Date;
    showTime?: boolean;
    disabled?: boolean;
    className?: string;
    customerTimezone?: string;
}

export function TimezoneDatePicker({
    value,
    onChange,
    label,
    minDate,
    maxDate,
    showTime = true,
    disabled = false,
    className = '',
    customerTimezone,
}: TimezoneDatePickerProps) {
    const { businessTimezone, isLoading } = useTimezone();
    const [localDate, setLocalDate] = useState<string>('');
    const [showCustomerTime, setShowCustomerTime] = useState(false);

    // Format the date for display in the business timezone
    useEffect(() => {
        if (value && businessTimezone) {
            const formattedDate = formatInUserTimezone(
                value,
                businessTimezone,
                showTime ? 'yyyy-MM-dd HH:mm' : 'yyyy-MM-dd'
            );
            setLocalDate(formattedDate);
        }
    }, [value, businessTimezone, showTime]);

    // Handle date input change
    const handleDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const inputValue = e.target.value;
        setLocalDate(inputValue);

        if (!inputValue) {
            onChange(null);
            return;
        }

        try {
            // Parse the input date in the business timezone
            const parsedDate = parse(
                inputValue,
                showTime ? 'yyyy-MM-dd HH:mm' : 'yyyy-MM-dd',
                new Date()
            );

            // Convert between timezones if needed
            const convertedDate = businessTimezone ? 
                convertTime(parsedDate.toISOString(), 'UTC', businessTimezone) : 
                parsedDate;

            // Ensure the time is within business hours
            if (showTime && !isBusinessHours(convertedDate, businessTimezone)) {
                const nextBusinessHour = getNextBusinessHour(convertedDate, businessTimezone);
                onChange(nextBusinessHour);
            } else {
                onChange(convertedDate);
            }
        } catch (error) {
            console.error('Error parsing date:', error);
        }
    };

    // Format the date for display in both timezones
    const getFormattedDate = () => {
        if (!value || !businessTimezone) return '';

        const businessTime = formatInUserTimezone(
            value,
            businessTimezone,
            showTime ? 'MMM d, yyyy h:mm a' : 'MMM d, yyyy'
        );

        if (customerTimezone && showCustomerTime) {
            const customerTime = formatInUserTimezone(
                value,
                customerTimezone,
                showTime ? 'MMM d, yyyy h:mm a' : 'MMM d, yyyy'
            );
            return `${businessTime} (${TIMEZONE_LABELS[businessTimezone] || 'Business'}) / ${customerTime} (${TIMEZONE_LABELS[customerTimezone] || 'Customer'})`;
        }

        return `${businessTime} (${TIMEZONE_LABELS[businessTimezone] || businessTimezone})`;
    };

    if (isLoading) {
        return <div>Loading timezone information...</div>;
    }

    return (
        <div className={`space-y-2 ${className}`}>
            {label && (
                <label className="block text-sm font-medium text-gray-700">
                    {label}
                </label>
            )}
            
            <div className="flex items-center space-x-2">
                <input
                    type={showTime ? 'datetime-local' : 'date'}
                    value={localDate}
                    onChange={handleDateChange}
                    min={minDate ? format(minDate, 'yyyy-MM-dd') : undefined}
                    max={maxDate ? format(maxDate, 'yyyy-MM-dd') : undefined}
                    disabled={disabled}
                    className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                />
                
                {customerTimezone && (
                    <button
                        type="button"
                        onClick={() => setShowCustomerTime(!showCustomerTime)}
                        className="text-sm text-indigo-600 hover:text-indigo-500"
                    >
                        {showCustomerTime ? 'Hide Customer Time' : 'Show Customer Time'}
                    </button>
                )}
            </div>
            
            {value && (
                <div className="text-sm text-gray-500">
                    {getFormattedDate()}
                </div>
            )}
        </div>
    );
} 