// frontend/src/components/autopilot/AutopilotPlanView.tsx
"use client";

import { useState, useEffect, useCallback, useRef } from 'react'; // Added useRef
import { apiClient } from '@/lib/api';
import { AutopilotMessage, TimelineEntry, CustomerBasicInfo } from '@/types'; // Added TimelineEntry, CustomerBasicInfo
import { Calendar, Clock, Edit, Trash2, User, Save, X, AlertCircle } from 'lucide-react';
import { format, parseISO, isValid } from 'date-fns'; // Added isValid

// Import TimelineItem component for rendering messages
import TimelineItem from '@/components/inbox/TimelineItem'; 
import MessageBox from '@/components/inbox/MessageBox'; // Potentially for inline reply/edit later


interface AutopilotPlanViewProps {
  businessId: number;
}

// Function to process an AutopilotMessage into a TimelineEntry
const processAutopilotMessageToTimelineEntry = (msg: AutopilotMessage): TimelineEntry | null => {
  if (!msg.id || !msg.content || !msg.scheduled_time) return null;

  // Autopilot messages are always 'outbound' and 'scheduled' from the perspective of the timeline
  // They are initiated by the business (even if automated)
  return {
    id: msg.id,
    type: 'scheduled', // Explicitly set as 'scheduled' type for timeline rendering
    content: msg.content,
    timestamp: msg.scheduled_time, // Use scheduled_time as the primary timestamp
    customer_id: msg.customer.id, // Assuming customer.id is available
    status: msg.status, // Pass the status directly
    // No AI drafts or contextual actions from Autopilot messages in this view directly
    is_faq_answer: false,
    appended_opt_in_prompt: false,
    ai_response: undefined,
    ai_draft_id: undefined,
    contextual_action: { // Add contextual action for edit/reschedule/cancel
      type: "AUTOPILOT_MESSAGE_ACTIONS",
      nudge_id: msg.id, // Use message ID as nudge_id for consistency in handling
      ai_suggestion: "Manage this scheduled message"
    }
  };
};

export default function AutopilotPlanView({ businessId }: AutopilotPlanViewProps) {
    const [messages, setMessages] = useState<AutopilotMessage[]>([]); // Raw scheduled messages
    const [timelineEntries, setTimelineEntries] = useState<TimelineEntry[]>([]); // Processed for timeline
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [editingMessageId, setEditingMessageId] = useState<number | null>(null);
    const [editedContent, setEditedContent] = useState<string>("");
    const [editedDateTime, setEditedDateTime] = useState<string>(""); // For datetime-local input
    const chatContainerRef = useRef<HTMLDivElement>(null);

    const fetchScheduledMessages = useCallback(async () => {
        if (!businessId) return;
        setIsLoading(true);
        setError(null);
        console.log(`Autopilot: Fetching scheduled messages for business ID: ${businessId}`);
        try {
            const response = await apiClient.get<AutopilotMessage[]>(`/review/autopilot-plan?business_id=${businessId}`);
            setMessages(response.data);
            
            // Process messages for timeline display
            const processed = response.data
                .map(processAutopilotMessageToTimelineEntry)
                .filter((entry): entry is TimelineEntry => entry !== null);
            setTimelineEntries(processed);

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

    // Scroll to bottom of timeline
    useEffect(() => {
        if (chatContainerRef.current) {
            chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
        }
    }, [timelineEntries]);


    const handleUpdateMessage = async (id: number, content: string, time: string) => {
        console.log(`Autopilot: Updating message ${id} to time ${time}`);
        try {
            // This endpoint updates a Message record (scheduled message)
            await apiClient.put(`/roadmap-workflow/update-time/${id}?source=scheduled`, {
                smsContent: content, // Use smsContent as that's what backend endpoint expects
                send_datetime_utc: time,
            });
            await fetchScheduledMessages(); // Refresh list after update
            setEditingMessageId(null); // Close edit mode
        } catch (err: any) {
            alert(`Error updating message: ${err.response?.data?.detail || err.message}`);
        }
    };
    
    const handleCancelMessage = async (id: number) => {
        console.log(`Autopilot: Cancelling message ${id}`);
        if (!window.confirm("Are you sure you want to cancel this scheduled message? This cannot be undone.")) {
            return;
        }
        try {
            // This endpoint deletes a Message record (scheduled message)
            await apiClient.delete(`/roadmap-workflow/${id}?source=scheduled`);
            await fetchScheduledMessages(); // Refresh list after delete
        } catch (err: any) {
            alert(`Error cancelling message: ${err.response?.data?.detail || err.message}`);
        }
    };

    // Handler for the contextual action click from TimelineItem
    const handleContextualAction = (messageId: number, actionType: string) => {
        const messageToActOn = messages.find(msg => msg.id === messageId);
        if (!messageToActOn) return;

        if (actionType === "AUTOPILOT_MESSAGE_ACTIONS") {
            // This action type means we open the edit/reschedule dialog
            setEditingMessageId(messageId);
            setEditedContent(messageToActOn.content);
            
            try {
                // Format for datetime-local input
                const dateForInput = format(parseISO(messageToActOn.scheduled_time), "yyyy-MM-dd'T'HH:mm");
                setEditedDateTime(dateForInput);
            } catch (e) {
                console.error("Error parsing scheduled_time for edit:", e);
                setEditedDateTime(""); // Clear if invalid
            }
        } else {
            console.warn(`Unsupported action type: ${actionType} for message ID: ${messageId}`);
        }
    };

    const handleSaveEdit = async () => {
        if (!editingMessageId || !editedDateTime) {
            alert("Please provide valid content and a valid date/time.");
            return;
        }
        const newUtcTime = new Date(editedDateTime).toISOString();
        await handleUpdateMessage(editingMessageId, editedContent, newUtcTime);
    };

    const handleCancelEdit = () => {
        setEditingMessageId(null);
        setEditedContent("");
        setEditedDateTime("");
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

    // Find the message currently being edited/rescheduled
    const editingPlan = messages.find(p => p.id === editingMessageId);

    return (
        <div className="p-6 bg-[#0B0E1C] rounded-lg h-full flex flex-col"> {/* Added flex-col for layout */}
            <div className="flex items-center gap-3 mb-4 flex-shrink-0">
                <Calendar className="text-blue-400" />
                <h2 className="text-2xl font-bold text-white">Nudge Autopilot Plan</h2>
            </div>
            <p className="text-gray-400 mb-6 flex-shrink-0">This is the flight plan for all future automated messages. You can edit or cancel any message before it's sent.</p>
            
            {editingPlan && (
                <div className="mb-6 p-4 bg-gray-800 rounded-lg border border-purple-500/50 shadow-lg flex-shrink-0">
                    <h3 className="text-lg font-semibold text-white mb-3">Edit/Reschedule Message</h3>
                    <p className="text-sm text-gray-400 mb-2">Recipient: {editingPlan.customer.name}</p>
                    <textarea
                        value={editedContent}
                        onChange={(e) => setEditedContent(e.target.value)}
                        className="w-full p-3 text-sm text-white bg-gray-900 border border-gray-700 rounded-md focus:ring-2 focus:ring-purple-500 outline-none resize-y mb-3"
                        rows={4}
                    />
                    <label htmlFor="edit-datetime" className="block text-sm font-medium text-gray-400 mb-1">Scheduled Date & Time (Local)</label>
                    <input
                        id="edit-datetime"
                        type="datetime-local"
                        value={editedDateTime}
                        onChange={(e) => setEditedDateTime(e.target.value)}
                        className="w-full p-3 text-sm text-white bg-gray-900 border border-gray-700 rounded-md focus:ring-2 focus:ring-purple-500 outline-none mb-4"
                    />
                    <div className="flex justify-end gap-3">
                        <button onClick={handleCancelEdit} className="px-4 py-2 text-sm text-white bg-gray-600 hover:bg-gray-700 rounded-md transition-colors">Cancel</button>
                        <button onClick={handleSaveEdit} className="px-4 py-2 text-sm text-white bg-purple-600 hover:bg-purple-700 rounded-md transition-colors">Save Changes</button>
                    </div>
                </div>
            )}

            <div ref={chatContainerRef} className="flex-1 overflow-y-auto space-y-3 p-2 bg-[#0B0E1C] rounded-lg border border-gray-800">
                {timelineEntries.length > 0 ? (
                    timelineEntries.map(entry => (
                        <TimelineItem 
                            key={entry.id} 
                            entry={entry} 
                            onEditDraft={() => {}} // Not used in this view (Autopilot msgs aren't drafts)
                            onDeleteDraft={() => {}} // Not directly used here, handled by contextual_action below
                            onActionClick={handleContextualAction} // Pass general action handler
                        />
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