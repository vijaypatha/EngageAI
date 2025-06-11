// frontend/src/components/EngagementPlanCard.tsx
'use client';

import React, { useState, useEffect } from 'react';
import { 
    LightbulbIcon, 
    MessageCircleIcon, 
    CalendarDaysIcon, 
    SendIcon, 
    XIcon, 
    Edit3Icon,
    ChevronDownIcon,
    ChevronUpIcon,
    Loader2,
    AlertTriangleIcon,
    Send,
    InfoIcon
} from 'lucide-react';
// Adjust this import path if your CoPilotNudge interface is defined elsewhere
import { CoPilotNudge } from './SentimentSpotlightCard'; 

// Define the structure of an individual message within the AI-drafted plan
export interface EngagementPlanMessage {
  text: string;
  suggested_delay_description: string; // e.g., "Send in 2 days", "Send 1 week after previous"
  // We will likely convert suggested_delay_description to an actual date/time for editing
  // or have a more structured delay (e.g., { unit: 'days', value: 2 }) from backend
}

// Define the expected structure of ai_suggestion_payload for this card type
interface StrategicPlanPayload {
  plan_objective: string;
  reason_to_believe: string;
  messages: EngagementPlanMessage[];
  // Potentially other fields like original_trigger_message_id, etc.
}

interface EngagementPlanCardProps {
  nudge: CoPilotNudge; // Nudge type will be STRATEGIC_ENGAGEMENT_OPPORTUNITY
  onActivatePlan: (
    nudgeId: number, 
    customerId: number, // customer_id will be on the nudge object
    finalMessages: Array<{ text: string; send_datetime_utc: string }> // Frontend sends finalized messages with absolute UTC times
  ) => Promise<void>;
  onDismiss: (nudgeId: number) => void;
  onViewConversation?: (nudge: CoPilotNudge) => void; // Optional, if context requires viewing chat
}

const EngagementPlanCard: React.FC<EngagementPlanCardProps> = ({
  nudge,
  onActivatePlan,
  onDismiss,
  onViewConversation,
}) => {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isEditingPlan, setIsEditingPlan] = useState(false); // To toggle detailed editing view

  const planPayload = nudge.ai_suggestion_payload as StrategicPlanPayload | null;

  // State for the messages in the plan, allowing them to be edited
  const [editableMessages, setEditableMessages] = useState<EngagementPlanMessage[]>([]);

  useEffect(() => {
    if (planPayload?.messages) {
      // Initialize editableMessages with a deep copy to avoid mutating the prop
      setEditableMessages(JSON.parse(JSON.stringify(planPayload.messages)));
    } else {
      setEditableMessages([]);
    }
  }, [planPayload?.messages]);

  const handleMessageTextChange = (index: number, newText: string) => {
    const updatedMessages = [...editableMessages];
    updatedMessages[index] = { ...updatedMessages[index], text: newText };
    setEditableMessages(updatedMessages);
  };

  const handleMessageTimingChange = (index: number, newTimingDesc: string) => {
    // For now, we just update the description.
    // A more complex implementation would parse this description or use a date picker
    // to set an actual `send_datetime_utc` for each message before activation.
    const updatedMessages = [...editableMessages];
    updatedMessages[index] = { ...updatedMessages[index], suggested_delay_description: newTimingDesc };
    setEditableMessages(updatedMessages);
  };

  const handleActivate = async () => {
    if (!nudge.customer_id) {
      setError("Customer ID is missing for this plan.");
      return;
    }
    if (editableMessages.some(msg => !msg.text.trim())) {
      setError("All messages in the plan must have content.");
      return;
    }

    setError(null);
    setIsLoading(true);

    // TODO: Convert editableMessages (with their suggested_delay_description)
    // into an array of { text: string; send_datetime_utc: string }
    // This conversion logic will be crucial and might involve:
    // 1. A robust date/time parsing library for the delay descriptions.
    // 2. A UI with proper date/time pickers for each message if `suggested_delay_description` is too free-form.
    // For MVP, we might send the descriptions and have backend try to parse, or simplify to fixed delays.
    
    // Placeholder: Simulating conversion for now.
    // This needs to be replaced with actual date calculation based on delays.
    const finalMessagesForApi = editableMessages.map((msg, index) => {
        const sendTime = new Date();
        sendTime.setDate(sendTime.getDate() + (index + 1) * 2); // Example: send every 2 days
        sendTime.setHours(10,0,0,0); // Default to 10 AM
        return {
            text: msg.text,
            send_datetime_utc: sendTime.toISOString(), // This should be a calculated UTC ISO string
        };
    });

    try {
      await onActivatePlan(nudge.id, nudge.customer_id, finalMessagesForApi);
      // If successful, parent component should remove the nudge from the list
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to activate engagement plan.");
      console.error("Error activating plan:", err);
    } finally {
      setIsLoading(false);
    }
  };

  if (!planPayload) {
    return (
      <div className="bg-slate-800 border border-red-500/60 p-4 rounded-lg shadow-md">
        <p className="text-red-400">Error: Engagement plan data is missing or invalid for this nudge.</p>
        <button onClick={() => onDismiss(nudge.id)} className="mt-2 text-xs text-slate-400 hover:text-red-300">Dismiss</button>
      </div>
    );
  }

  return (
    <div className={`bg-slate-800/90 border ${isEditingPlan ? 'border-purple-500/70 shadow-md shadow-purple-500/20' : 'border-purple-500/50'} bg-gradient-to-br from-slate-800/80 to-purple-900/20 rounded-xl p-3 sm:p-4 shadow-lg flex flex-col h-full backdrop-blur-sm transition-all hover:shadow-purple-500/10`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center">
          <LightbulbIcon className="w-5 h-5 sm:w-6 sm:h-6 mr-2 flex-shrink-0 text-purple-400" />
          <h3 className="text-base sm:text-md font-semibold text-slate-100 truncate">
            AI Engagement Plan
            {nudge.customer_name && <span className="text-xs text-slate-400 font-normal ml-1.5">for {nudge.customer_name}</span>}
          </h3>
        </div>
        <button
            onClick={() => setIsEditingPlan(!isEditingPlan)}
            className="p-1.5 text-slate-400 hover:text-purple-300 transition-colors rounded-md hover:bg-slate-700/50"
            title={isEditingPlan ? "Collapse Plan Details" : "Expand & Edit Plan"}
          >
            {isEditingPlan ? <ChevronUpIcon className="w-4 h-4 sm:w-5 sm:h-5" /> : <ChevronDownIcon className="w-4 h-4 sm:w-5 sm:h-5" />}
        </button>
      </div>

      {/* Triggering Context Snippet */}
      {nudge.message_snippet && (
        <div className="bg-slate-700/50 p-2 rounded-md text-slate-300 italic mb-2 text-xs">
          Context: "{nudge.message_snippet}"
        </div>
      )}

      {/* Plan Objective & Reason to Believe (Always Visible) */}
      <div className="bg-purple-900/20 border border-purple-800/50 p-2.5 rounded-md mb-3 text-xs">
        <p className="font-semibold text-purple-300 mb-0.5">AI Plan Objective:</p>
        <p className="text-slate-300 leading-snug mb-1.5">{planPayload.plan_objective}</p>
        <p className="font-semibold text-purple-300 mb-0.5">Reason to Believe:</p>
        <p className="text-slate-300 leading-snug">{planPayload.reason_to_believe}</p>
      </div>
      
      {/* Collapsible Message Sequence Editor/Viewer */}
      {isEditingPlan && (
        <div className="space-y-3 mb-3 transition-all duration-300 ease-in-out flex-grow">
          <p className="text-xs text-slate-400">Edit suggested messages and timing:</p>
          {editableMessages.map((msg, index) => (
            <div key={index} className="p-2.5 bg-slate-700/30 rounded-md border border-slate-600/50">
              <label htmlFor={`msg-text-${nudge.id}-${index}`} className="block text-xs font-medium text-slate-300 mb-1">
                Message {index + 1} Text:
              </label>
              <textarea
                id={`msg-text-${nudge.id}-${index}`}
                value={msg.text}
                onChange={(e) => handleMessageTextChange(index, e.target.value)}
                rows={3}
                className="w-full bg-slate-600/70 border border-slate-500 text-slate-200 text-xs rounded-md p-2 focus:ring-1 focus:ring-purple-500 focus:border-purple-500 disabled:opacity-70"
                disabled={isLoading}
              />
              <label htmlFor={`msg-timing-${nudge.id}-${index}`} className="block text-xs font-medium text-slate-300 mt-1.5 mb-1">
                Suggested Timing:
              </label>
              <input
                type="text"
                id={`msg-timing-${nudge.id}-${index}`}
                value={msg.suggested_delay_description}
                onChange={(e) => handleMessageTimingChange(index, e.target.value)}
                placeholder="e.g., In 2 days, Next Monday at 10 AM"
                className="w-full bg-slate-600/70 border border-slate-500 text-slate-200 text-xs rounded-md p-2 focus:ring-1 focus:ring-purple-500 focus:border-purple-500 disabled:opacity-70"
                disabled={isLoading}
              />
            </div>
          ))}
        </div>
      )}
      {!isEditingPlan && ( // Summary view of the plan when not editing
         <div className="space-y-1.5 mb-3 text-xs text-slate-300/90 flex-grow">
            <p className="font-medium text-slate-200">Proposed Plan ({editableMessages.length} steps):</p>
            {editableMessages.map((msg, index) => (
                <div key={index} className="pl-2 border-l-2 border-purple-700/50">
                    <p className="text-purple-300/80 text-[11px]">{msg.suggested_delay_description}</p>
                    <p className="italic">"{msg.text.substring(0,60)}{msg.text.length > 60 ? '...' : ''}"</p>
                </div>
            ))}
        </div>
      )}

      {error && (
        <p className="text-xs text-red-400 mb-2 flex items-center">
          <AlertTriangleIcon className="w-4 h-4 mr-1 flex-shrink-0" /> {error}
        </p>
      )}

      {/* Action Buttons */}
      <div className="mt-auto pt-3 border-t border-slate-700/50 space-y-2">
        <button
          onClick={handleActivate}
          disabled={isLoading || editableMessages.length === 0}
          className="w-full flex justify-center items-center px-3 py-2.5 border border-transparent text-sm font-semibold rounded-md shadow-sm text-white bg-purple-600 hover:bg-purple-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500 focus:ring-offset-slate-800 disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {isLoading ? <Loader2 className="w-5 h-5 animate-spin mr-2"/> : <Send className="w-4 h-4 mr-2"/>}
          Activate Plan
        </button>
        <div className="flex space-x-2">
            {onViewConversation && ( // Conditionally render View Chat
                 <button
                    onClick={() => onViewConversation(nudge)}
                    disabled={isLoading}
                    className="flex-1 flex justify-center items-center px-3 py-1.5 border border-slate-600 hover:border-slate-500 text-xs font-medium rounded-md text-slate-300 hover:text-purple-300 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-slate-500 focus:ring-offset-slate-800 disabled:opacity-60"
                    >
                <MessageCircleIcon className="w-3.5 h-3.5 mr-1.5" /> View Chat
                </button>
            )}
            <button
              onClick={() => onDismiss(nudge.id)}
              disabled={isLoading}
              title="Dismiss this plan suggestion"
              className={`${onViewConversation ? 'flex-1 sm:flex-none' : 'w-full'} flex justify-center items-center sm:px-3 py-1.5 border border-slate-600 hover:border-slate-500 text-xs font-medium rounded-md text-slate-400 hover:text-red-400 focus:outline-none disabled:opacity-60`}
            >
              <XIcon className="w-3.5 h-3.5 mr-1.5" /> Dismiss Plan
            </button>
        </div>
      </div>
      <p className="text-right text-[10px] text-slate-500 mt-2">
         Nudge ID: {nudge.id} | Type: Strategic Plan
      </p>
    </div>
  );
};

export default EngagementPlanCard;
