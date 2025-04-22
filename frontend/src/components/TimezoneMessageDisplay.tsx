import React from 'react';
import { useTimezone } from '@/hooks/useTimezone';
import { formatInUserTimezone, TIMEZONE_LABELS } from '@/lib/timezone';

interface Message {
    id: number;
    content: string;
    sendTime: string;
    status: string;
    customerTimezone?: string;
}

interface TimezoneMessageDisplayProps {
    message: Message;
    showCustomerTime?: boolean;
    className?: string;
}

export function TimezoneMessageDisplay({
    message,
    showCustomerTime = false,
    className = '',
}: TimezoneMessageDisplayProps) {
    const { businessTimezone } = useTimezone();
    
    // Format time in business timezone
    const businessTime = formatInUserTimezone(
        new Date(message.sendTime),
        businessTimezone,
        'h:mm a'
    );
    
    // Format time in customer timezone if available and requested
    const customerTime = showCustomerTime && message.customerTimezone
        ? formatInUserTimezone(
            new Date(message.sendTime),
            message.customerTimezone,
            'h:mm a'
        )
        : null;

    return (
        <div className={`flex flex-col ${className}`}>
            <div className="flex items-start justify-between">
                <p className="text-gray-900">{message.content}</p>
                <div className="flex flex-col items-end ml-4 text-sm">
                    <div className="text-gray-600">
                        {businessTime}{' '}
                        <span className="text-gray-500">
                            ({TIMEZONE_LABELS[businessTimezone] || businessTimezone})
                        </span>
                    </div>
                    {customerTime && (
                        <div className="text-gray-500">
                            {customerTime}{' '}
                            <span className="text-gray-400">
                                ({TIMEZONE_LABELS[message.customerTimezone!] || message.customerTimezone})
                            </span>
                        </div>
                    )}
                </div>
            </div>
            <div className="mt-1 text-sm text-gray-500">
                Status: {message.status}
            </div>
        </div>
    );
} 