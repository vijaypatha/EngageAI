import React from 'react';
import { startOfWeek, endOfWeek, isWithinInterval } from 'date-fns';
import { useTimezone } from '@/hooks/useTimezone';
import { convertTime, formatInUserTimezone } from '@/lib/timezone';
import { TimezoneMessageDisplay } from './TimezoneMessageDisplay';

interface Message {
    id: number;
    content: string;
    sendTime: string;
    status: string;
    customerTimezone?: string;
}

interface TimezoneMessageListProps {
    messages: Message[];
    showCustomerTime?: boolean;
}

export function TimezoneMessageList({
    messages,
    showCustomerTime = false,
}: TimezoneMessageListProps) {
    const { businessTimezone } = useTimezone();

    // Group messages by week
    const messagesByWeek = React.useMemo(() => {
        const weeks: { [key: string]: Message[] } = {};
        
        messages.forEach(message => {
            // Convert message time to business timezone
            const messageDate = convertTime(
                new Date(message.sendTime).toISOString(),
                'UTC',
                businessTimezone
            );
            
            // Get the start of the week (Monday) for this message
            const weekStart = startOfWeek(messageDate, { weekStartsOn: 1 });
            const weekKey = weekStart.toISOString();
            
            if (!weeks[weekKey]) {
                weeks[weekKey] = [];
            }
            
            weeks[weekKey].push(message);
        });
        
        // Sort messages within each week by send time (most recent first)
        Object.values(weeks).forEach(weekMessages => {
            weekMessages.sort((a, b) => 
                new Date(b.sendTime).getTime() - new Date(a.sendTime).getTime()
            );
        });
        
        return weeks;
    }, [messages, businessTimezone]);

    // Sort weeks by date (most recent first)
    const sortedWeeks = React.useMemo(() => {
        return Object.entries(messagesByWeek)
            .sort(([weekA], [weekB]) => 
                new Date(weekB).getTime() - new Date(weekA).getTime()
            );
    }, [messagesByWeek]);

    if (messages.length === 0) {
        return (
            <div className="text-center text-gray-500 py-8">
                No messages scheduled
            </div>
        );
    }

    return (
        <div className="space-y-8">
            {sortedWeeks.map(([weekKey, weekMessages]) => {
                const weekStart = new Date(weekKey);
                const weekEnd = endOfWeek(weekStart, { weekStartsOn: 1 });
                
                // Format week range in business timezone
                const weekRange = `${
                    formatInUserTimezone(weekStart, businessTimezone, 'MMM d')
                } - ${
                    formatInUserTimezone(weekEnd, businessTimezone, 'MMM d')
                }`;

                return (
                    <div key={weekKey} className="space-y-4">
                        <h3 className="font-medium text-gray-900">
                            {weekRange}
                        </h3>
                        <div className="space-y-4">
                            {weekMessages.map(message => (
                                <TimezoneMessageDisplay
                                    key={message.id}
                                    message={message}
                                    showCustomerTime={showCustomerTime}
                                    className="bg-white rounded-lg shadow p-4"
                                />
                            ))}
                        </div>
                    </div>
                );
            })}
        </div>
    );
} 