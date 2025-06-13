// frontend/src/components/autopilot/AutopilotPlanView.tsx
"use client";

import { useState, useEffect, useCallback } from 'react';
import { apiClient } from '@/lib/api';
import { AutopilotMessage } from '@/types'; // AutopilotMessage type from types/index.ts
import { Calendar, Clock, Edit, Trash2, User, Save, X, AlertCircle } from 'lucide-react';
import { format, parseISO } from 'date-fns';

interface AutopilotPlanViewProps {
  businessId: number;
}

// Sub-component for a single scheduled message item
const AutopilotItem = ({ item, onUpdate, onCancel }: { item: AutopilotMessage, onUpdate: (id: number, content: string, time: string) => Promise<void>, onCancel: (id: number) => Promise<void> }) => {
  const [isEditing, setIsEditing] = useState(false);
  const [content, setContent] = useState(item.content); // Use item.content
  
  // Format the scheduled_time from ISO string to a local datetime-local input format
  const formatForInput = (isoString: string) => {
    try {
      return format(parseISO(isoString), "yyyy-MM-dd'T'HH:mm");
    } catch {
      return "";
    }
  };
  const [scheduledTime, setScheduledTime] = useState(formatForInput(item.scheduled_time)); // Use item.scheduled_time

  const handleSave = async () => {
    if (!scheduledTime) {
        // Changed from alert() to a more user-friendly inline message or modal if this were a full app.
        // For now, keeping alert as per existing pattern for minor notifications.
        alert("Please select a valid date and time.");
        return;
    }
    const newUtcTime = new Date(scheduledTime).toISOString();
    await onUpdate(item.id, content, newUtcTime);
    setIsEditing(false);
  };

  const handleCancel = () => {
    // Changed from window.confirm() to a more user-friendly modal if this were a full app.
    // For now, keeping window.confirm as per existing pattern for minor confirmations.
    if (window.confirm("Are you sure you want to cancel this scheduled message? This cannot be undone.")) {
      onCancel(item.id);
    }
  };

  return (
    <div className="bg-gray-800 p-4 rounded-lg flex flex-col md:flex-row md:items-center justify-between gap-4 transition-all hover:bg-gray-700/50">
      <div className="flex-1 min-w-0">
        <div className="flex items-center text-sm text-gray-400 mb-2">
          <User size={14} className="mr-2" />
          <span>{item.customer.name}</span> {/* Use item.customer.name */}
        </div>
        {isEditing ? (
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="w-full bg-gray-900 p-2 rounded-md border border-gray-600 focus:ring-2 focus:ring-blue-500 outline-none text-white"
            rows={3}
          />
        ) : (
          <p className="text-white text-base whitespace-pre-wrap">{item.content}</p>
        )}
      </div>
      <div className="flex-shrink-0 flex flex-col md:items-end md:text-right gap-2">
        {isEditing ? (
           <input
                type="datetime-local"
                value={scheduledTime}
                onChange={(e) => setScheduledTime(e.target.value)}
                className="bg-gray-900 p-2 rounded-md border border-gray-600 text-sm text-white focus:ring-2 focus:ring-blue-500 outline-none"
            />
        ) : (
            <div className="flex items-center gap-2 text-sm text-blue-300">
                <Clock size={14} />
                <span>{format(parseISO(item.scheduled_time), "MMM d, yyyy 'at' p")}</span> {/* Use item.scheduled_time */}
            </div>
        )}
        <div className="flex items-center gap-2 mt-2">
          {isEditing ? (
            <>
              <button onClick={handleSave} className="p-2 bg-green-600 hover:bg-green-500 rounded-md transition-colors" title="Save Changes"><Save size={16} /></button>
              <button onClick={() => setIsEditing(false)} className="p-2 bg-gray-600 hover:bg-gray-500 rounded-md transition-colors" title="Cancel Edit"><X size={16} /></button>
            </>
          ) : (
            <>
              <button onClick={() => setIsEditing(true)} className="p-2 bg-blue-600 hover:bg-blue-500 rounded-md transition-colors" title="Edit"><Edit size={16} /></button>
              <button onClick={handleCancel} className="p-2 bg-red-700 hover:bg-red-600 rounded-md transition-colors" title="Cancel"><Trash2 size={16} /></button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default function AutopilotPlanView({ businessId }: AutopilotPlanViewProps) {
    const [messages, setMessages] = useState<AutopilotMessage[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const fetchScheduledMessages = useCallback(async () => {
        if (!businessId) return;
        setIsLoading(true);
        setError(null);
        console.log(`Autopilot: Fetching scheduled messages for business ID: ${businessId}`);
        try {
            // API call to the new backend endpoint
            const response = await apiClient.get<AutopilotMessage[]>(`/review/autopilot-plan?business_id=${businessId}`);
            setMessages(response.data);
            console.log(`Autopilot: Found ${response.data.length} scheduled messages.`);
        } catch (err: any) {
            console.error("Failed to fetch autopilot plan:", err);
            setError(err.response?.data?.detail || "Could not load the scheduled plan.");
        } finally {
            setIsLoading(false);
        }
    }, [businessId]);

    useEffect(() => {
        fetchScheduledMessages();
    }, [fetchScheduledMessages]);

    const handleUpdateMessage = async (id: number, content: string, time: string) => {
        console.log(`Autopilot: Updating message ${id} to time ${time}`);
        try {
            // This endpoint updates a Message record (scheduled message)
            await apiClient.put(`/roadmap-workflow/update-time/${id}?source=scheduled`, {
                smsContent: content, // Pass the content to be updated
                send_datetime_utc: time, // Pass the new scheduled time
            });
            await fetchScheduledMessages(); // Refresh list after update
        } catch (err: any) {
            alert(`Error updating message: ${err.response?.data?.detail || err.message}`);
        }
    };
    
    const handleCancelMessage = async (id: number) => {
        console.log(`Autopilot: Cancelling message ${id}`);
        try {
            // This endpoint deletes a Message record (scheduled message)
            await apiClient.delete(`/roadmap-workflow/${id}?source=scheduled`);
            await fetchScheduledMessages(); // Refresh list after delete
        } catch (err: any) {
            alert(`Error cancelling message: ${err.response?.data?.detail || err.message}`);
        }
    };

    if (isLoading) {
        return <div className="p-6 text-center text-gray-400">Loading flight plan...</div>;
    }

    if (error) {
        return (
            <div className="p-6 text-center text-red-400 bg-red-900/20 rounded-lg">
                <AlertCircle className="mx-auto w-8 h-8 mb-2" />
                <p>Failed to load Autopilot Plan</p>
                <p className="text-xs text-red-500 mt-1">{error}</p>
            </div>
        );
    }

    return (
        <div className="p-6 bg-[#0B0E1C] rounded-lg">
            <div className="flex items-center gap-3 mb-4">
                <Calendar className="text-blue-400" />
                <h2 className="text-2xl font-bold text-white">Nudge Autopilot Plan</h2>
            </div>
            <p className="text-gray-400 mb-6">This is the flight plan for all future automated messages. You can edit or cancel any message before it's sent.</p>
            
            <div className="space-y-4">
                {messages.length > 0 ? (
                    messages.map(item => (
                        <AutopilotItem key={item.id} item={item} onUpdate={handleUpdateMessage} onCancel={handleCancelMessage} />
                    ))
                ) : (
                    <div className="text-center py-10 px-6 bg-gray-800 rounded-lg">
                        <Clock size={40} className="mx-auto text-gray-500" />
                        <p className="mt-4 font-semibold text-white">Autopilot is Clear</p>
                        <p className="text-gray-400 text-sm">There are no messages scheduled for the future.</p>
                    </div>
                )}
            </div>
        </div>
    );
}