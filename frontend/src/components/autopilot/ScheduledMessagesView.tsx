// frontend/src/components/autopilot/ScheduledMessagesView.tsx
"use client";

import { useState, useEffect, useCallback, useMemo, FC } from 'react';
import { apiClient } from '@/lib/api';
import { AutopilotMessage } from '@/types';
import { Clock, Edit, Trash2, Loader2, AlertCircle, Save, X, User } from 'lucide-react';
import { format, parseISO, isValid, isToday, isTomorrow, isThisWeek, addWeeks, startOfWeek, endOfWeek } from 'date-fns';

interface ScheduledMessagesViewProps {
  businessId: number;
}

// --- PlanCard Sub-Component ---
// This component renders a single scheduled message card and its editing state.
const PlanCard: FC<{
    message: AutopilotMessage;
    isEditing: boolean;
    isSubmitting: boolean;
    editedContent: string;
    editedDateTime: string;
    onEdit: (message: AutopilotMessage) => void;
    onSave: () => void;
    onCancel: () => void;
    onDelete: (id: number) => void;
    setEditedContent: (value: string) => void;
    setEditedDateTime: (value: string) => void;
}> = ({ message, isEditing, isSubmitting, editedContent, editedDateTime, onEdit, onSave, onCancel, onDelete, setEditedContent, setEditedDateTime }) => {
    
    const formattedDateTime = useMemo(() => {
        const date = parseISO(message.scheduled_time);
        return isValid(date) ? format(date, "EEE, MMM d 'at' p") : "Invalid date";
    }, [message.scheduled_time]);

    if (isEditing) {
        return (
            <div className="p-4 bg-slate-700/60 border border-purple-500 rounded-lg shadow-xl flex flex-col gap-4 animate-fade-in">
                <div className="flex items-center gap-2 text-sm text-purple-300 font-semibold">
                    <User size={16} /> To: {message.customer.customer_name}
                </div>
                <textarea
                    value={editedContent}
                    onChange={(e) => setEditedContent(e.target.value)}
                    className="w-full p-2 rounded bg-slate-800 border border-slate-600 text-white text-sm"
                    rows={4}
                />
                <input
                    type="datetime-local"
                    value={editedDateTime}
                    onChange={(e) => setEditedDateTime(e.target.value)}
                    className="w-full p-2 rounded bg-slate-800 border border-slate-600 text-white text-sm"
                />
                <div className="flex justify-end gap-2 mt-2">
                    <button onClick={onCancel} disabled={isSubmitting} className="px-3 py-1.5 text-sm rounded-md bg-slate-600 hover:bg-slate-500 text-white flex items-center gap-1.5"><X size={14} /> Cancel</button>
                    <button onClick={onSave} disabled={isSubmitting} className="px-3 py-1.5 text-sm rounded-md bg-purple-600 hover:bg-purple-700 text-white flex items-center gap-1.5">
                        {isSubmitting ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Save
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div className="p-4 bg-slate-800/80 border border-slate-700 rounded-lg shadow-lg flex flex-col justify-between group relative">
            <div>
                <div className="flex justify-between items-start">
                    <p className="text-sm font-semibold text-purple-300 flex items-center gap-2">
                        <User size={16} /> {message.customer.customer_name}
                    </p>
                    <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button onClick={() => onEdit(message)} className="p-1.5 bg-blue-600/50 hover:bg-blue-600 rounded text-white"><Edit size={12} /></button>
                        <button onClick={() => onDelete(message.id)} disabled={isSubmitting} className="p-1.5 bg-red-600/50 hover:bg-red-600 rounded text-white"><Trash2 size={12} /></button>
                    </div>
                </div>
                <p className="mt-2 text-sm text-slate-300 whitespace-pre-wrap break-words">{message.content}</p>
            </div>
            <div className="mt-3 pt-3 border-t border-slate-700/50 text-xs text-slate-400 flex items-center gap-2">
                <Clock size={12} /> {formattedDateTime}
            </div>
        </div>
    );
};


// --- Main View Component ---
export default function ScheduledMessagesView({ businessId }: ScheduledMessagesViewProps) {
    const [messages, setMessages] = useState<AutopilotMessage[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [isSubmitting, setIsSubmitting] = useState(false);

    const [editingMessageId, setEditingMessageId] = useState<number | null>(null);
    const [editedContent, setEditedContent] = useState<string>("");
    const [editedDateTime, setEditedDateTime] = useState<string>("");

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
        } catch (err: any) {
            setError(err.response?.data?.detail || "Could not load the scheduled plan.");
        } finally {
            if (showLoadingIndicator) setIsLoading(false);
        }
    }, [businessId]);

    useEffect(() => {
        fetchScheduledMessages();
    }, [fetchScheduledMessages]);

    const handleEdit = (message: AutopilotMessage) => {
        setEditingMessageId(message.id);
        setEditedContent(message.content);
        // Format for the datetime-local input
        setEditedDateTime(format(parseISO(message.scheduled_time), "yyyy-MM-dd'T'HH:mm"));
    };

    const handleCancelEdit = () => {
        setEditingMessageId(null);
        setEditedContent("");
        setEditedDateTime("");
    };

    const handleSaveEdit = async () => {
        if (!editingMessageId) return;
        setIsSubmitting(true);
        try {
            const newUtcTime = new Date(editedDateTime).toISOString();
            // Using the endpoint from the original file context
            await apiClient.put(`/roadmap-workflow/update-time/${editingMessageId}?source=scheduled`, {
                smsContent: editedContent,
                send_datetime_utc: newUtcTime,
            });
            await fetchScheduledMessages(false); // Re-fetch data without full loader
            handleCancelEdit();
        } catch (err: any) {
            setError(err.response?.data?.detail || "Failed to save changes.");
        } finally {
            setIsSubmitting(false);
        }
    };
    
    const handleDelete = async (id: number) => {
        if (!window.confirm("Are you sure you want to cancel this scheduled message?")) return;
        setIsSubmitting(true);
        try {
            // Using the endpoint from the original file context
            await apiClient.delete(`/roadmap-workflow/${id}?source=scheduled`);
            setMessages(prev => prev.filter(m => m.id !== id)); // Optimistic UI update
            // await fetchScheduledMessages(false); // Or re-fetch
        } catch (err: any) {
            setError(err.response?.data?.detail || "Failed to cancel message.");
            fetchScheduledMessages(false); // Re-fetch on error to sync state
        } finally {
            setIsSubmitting(false);
        }
    };

    const groupedMessages = useMemo(() => {
        const groups: Record<string, AutopilotMessage[]> = {};
        const now = new Date();
        const weekOptions = { weekStartsOn: 1 as const };
        const startOfNextWeek = startOfWeek(addWeeks(now, 1), weekOptions);
        const endOfNextWeek = endOfWeek(addWeeks(now, 1), weekOptions);
        
        messages.forEach(msg => {
            let groupKey = 'Later';
            const entryDate = parseISO(msg.scheduled_time);
            if (isValid(entryDate)) {
                if (isToday(entryDate)) groupKey = 'Today';
                else if (isTomorrow(entryDate)) groupKey = 'Tomorrow';
                else if (isThisWeek(entryDate, weekOptions)) groupKey = 'This Week';
                else if (entryDate >= startOfNextWeek && entryDate <= endOfNextWeek) groupKey = 'Next Week';
                else groupKey = format(entryDate, 'MMMM yyyy');
            } else {
                groupKey = 'Undated';
            }
            if (!groups[groupKey]) groups[groupKey] = [];
            groups[groupKey].push(msg);
        });
        return groups;
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
            <div className="text-center py-10 px-6 bg-slate-800/50 rounded-lg">
                <Clock size={40} className="mx-auto text-slate-500" />
                <p className="mt-4 font-semibold text-white">No Messages Scheduled</p>
                <p className="text-slate-400 text-sm">The flight plan is clear. Autopilot is standing by.</p>
            </div>
        );
    }

    return (
        <div className="space-y-10">
            {groupOrder.map(groupName => (
                <div key={groupName}>
                    <h3 className="text-lg font-semibold text-slate-300 mb-4 tracking-wide">{groupName}</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {groupedMessages[groupName].map(message => (
                            <PlanCard
                                key={message.id}
                                message={message}
                                isEditing={editingMessageId === message.id}
                                isSubmitting={isSubmitting}
                                editedContent={editedContent}
                                editedDateTime={editedDateTime}
                                onEdit={handleEdit}
                                onSave={handleSaveEdit}
                                onCancel={handleCancelEdit}
                                onDelete={handleDelete}
                                setEditedContent={setEditedContent}
                                setEditedDateTime={setEditedDateTime}
                            />
                        ))}
                    </div>
                </div>
            ))}
        </div>
    );
}