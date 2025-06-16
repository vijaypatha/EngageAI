// frontend/src/components/autopilot/ScheduledMessagesView.tsx
"use client";

import { useState, useEffect, useCallback, useMemo, FC } from 'react';
import { apiClient } from '@/lib/api';
import { AutopilotMessage } from '@/types';
import { Clock, Loader2, User, ChevronDown, CheckCircle } from 'lucide-react';
import { format, parseISO, isValid, isToday, isTomorrow, isThisWeek, addWeeks, startOfWeek, endOfWeek } from 'date-fns';
import clsx from 'clsx';

interface ScheduledMessagesViewProps {
  businessId: number;
}

// --- PlanCard Sub-Component ---
const PlanCard: FC<{ message: AutopilotMessage }> = ({ message }) => {
    
    const formattedDateTime = useMemo(() => {
        const date = parseISO(message.scheduled_time);
        return isValid(date) ? format(date, "EEE, MMM d 'at' p") : "Invalid date";
    }, [message.scheduled_time]);

    return (
        <div className="p-4 bg-slate-800 border border-slate-700 rounded-lg shadow-lg flex flex-col justify-between group relative h-full">
            <div>
                <div className="flex justify-between items-start">
                    <p className="text-sm font-semibold text-purple-300 flex items-center gap-2">
                        <User size={16} /> {message.customer.customer_name}
                    </p>
                    {/* Hover-to-show edit/delete buttons can be added here in a future iteration */}
                </div>
                <p className="mt-2 text-sm text-slate-300 whitespace-pre-wrap break-words">{message.content}</p>
            </div>
            <div className="mt-3 pt-3 border-t border-slate-700/50 text-xs text-slate-400 flex items-center gap-2">
                <Clock size={12} /> {formattedDateTime}
            </div>
        </div>
    );
};


// --- Main View Component with Accordion UI ---
export default function ScheduledMessagesView({ businessId }: ScheduledMessagesViewProps) {
    const [messages, setMessages] = useState<AutopilotMessage[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // State for the accordion
    const [expandedGroup, setExpandedGroup] = useState<string | null>(null);

    const getGroupKey = (message: AutopilotMessage): string => {
        const now = new Date();
        const weekOptions = { weekStartsOn: 1 as const };
        const startOfNextWeek = startOfWeek(addWeeks(now, 1), weekOptions);
        const endOfNextWeek = endOfWeek(addWeeks(now, 1), weekOptions);
        
        const entryDate = parseISO(message.scheduled_time);
        if (isValid(entryDate)) {
            if (isToday(entryDate)) return 'Today';
            if (isTomorrow(entryDate)) return 'Tomorrow';
            if (isThisWeek(entryDate, weekOptions)) return 'This Week';
            if (entryDate >= startOfNextWeek && entryDate <= endOfNextWeek) return 'Next Week';
            return format(entryDate, 'MMMM yyyy');
        }
        return 'Undated';
    };

    const fetchScheduledMessages = useCallback(async (showLoadingIndicator = true) => {
        if (!businessId) return;
        if (showLoadingIndicator) setIsLoading(true);
        setError(null);

        try {
            const response = await apiClient.get<AutopilotMessage[]>(`/review/autopilot-plan?business_id=${businessId}`);
            const sortedMessages = response.data.sort((a, b) => {
                const timeA = a.scheduled_time ? parseISO(a.scheduled_time).getTime() : 0;
                const timeB = b.scheduled_time ? parseISO(b.scheduled_time).getTime() : 0;
                return timeA - timeB;
            });
            setMessages(sortedMessages);
            // Automatically expand the first group if it exists
            if (sortedMessages.length > 0) {
                const firstGroupKey = getGroupKey(sortedMessages[0]);
                setExpandedGroup(firstGroupKey);
            }
        } catch (err: any) {
            setError(err.response?.data?.detail || "Could not load the scheduled plan.");
        } finally {
            if (showLoadingIndicator) setIsLoading(false);
        }
    }, [businessId]); // getGroupKey is now defined inside so it doesn't need to be a dependency

    useEffect(() => {
        fetchScheduledMessages();
    }, [fetchScheduledMessages]);


    const groupedMessages = useMemo(() => {
        return messages.reduce((acc, msg) => {
            const groupKey = getGroupKey(msg);
            if (!acc[groupKey]) {
                acc[groupKey] = [];
            }
            acc[groupKey].push(msg);
            return acc;
        }, {} as Record<string, AutopilotMessage[]>);
    }, [messages]);

    const groupOrder = useMemo(() => {
        const order = ['Today', 'Tomorrow', 'This Week', 'Next Week'];
        const monthKeys = Object.keys(groupedMessages)
          .filter(key => !order.includes(key) && key !== 'Undated')
          .sort((a, b) => new Date(`1 ${a}`).getTime() - new Date(`1 ${b}`).getTime());
        return [...order, ...monthKeys, 'Undated'].filter(key => groupedMessages[key]?.length > 0);
    }, [groupedMessages]);

    if (isLoading) return <div className="flex justify-center p-10"><Loader2 className="w-8 h-8 animate-spin text-purple-400" /></div>;
    
    if (error) return <div className="text-center p-6 bg-red-900/20 text-red-400 rounded-lg"><p>{error}</p></div>;

    if (messages.length === 0) {
        return (
            <div className="text-center py-12 px-6 bg-slate-800/50 rounded-lg border border-slate-700">
                <CheckCircle className="w-14 h-14 text-green-500 mx-auto mb-4" />
                <p className="font-semibold text-white text-lg">Flight Plan is Clear!</p>
                <p className="text-slate-400 text-sm">No messages are currently scheduled.</p>
            </div>
        );
    }

    return (
        <div className="space-y-2">
            {groupOrder.map(groupName => {
                const isExpanded = expandedGroup === groupName;
                const items = groupedMessages[groupName];
                return (
                    <div key={groupName} className="bg-slate-800/50 border border-slate-700 rounded-lg overflow-hidden transition-all duration-300">
                        {/* --- Accordion Header --- */}
                        <div 
                            className="flex items-center justify-between p-4 cursor-pointer hover:bg-slate-800"
                            onClick={() => setExpandedGroup(isExpanded ? null : groupName)}
                        >
                            <div className="flex items-center gap-3">
                                <h3 className="font-bold text-slate-100">{groupName}</h3>
                                <span className="text-xs font-semibold bg-slate-700 text-slate-300 px-2 py-0.5 rounded-full">{items.length}</span>
                            </div>
                            <ChevronDown className={clsx("w-5 h-5 text-slate-400 transition-transform", { "rotate-180": isExpanded })} />
                        </div>
                        {/* --- Expanded Content with Cards --- */}
                        {isExpanded && (
                            <div className="p-4 border-t border-slate-700">
                                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                                    {items.map(message => (
                                        <PlanCard
                                            key={message.id}
                                            message={message}
                                        />
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                )
            })}
        </div>
    );
}
