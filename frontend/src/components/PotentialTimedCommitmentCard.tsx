// frontend/src/components/PotentialTimedCommitmentCard.tsx
'use client';

import React, { useState, useEffect } from 'react';
import { 
    CalendarClockIcon, 
    XIcon, 
    MessageSquareTextIcon, 
    CheckCircle2Icon, 
    AlertTriangleIcon, 
    Loader2, 
    InfoIcon, 
    Edit3Icon, 
    ChevronDownIcon, 
    ChevronUpIcon 
} from 'lucide-react';
// Adjust this import path if your CoPilotNudge interface is defined elsewhere
import { CoPilotNudge } from './SentimentSpotlightCard'; 

interface PotentialEventPayload {
  detected_text_snippet?: string;
  parsed_datetime_utc_suggestion?: string | null;
  parsed_purpose_suggestion?: string | null;
  raw_detected_time_phrase?: string | null;
  raw_detected_date_phrase?: string | null;
}

interface PotentialTimedCommitmentCardProps {
  nudge: CoPilotNudge;
  onConfirm: (nudgeId: number, confirmedDatetimeUtc: string, confirmedPurpose: string) => Promise<void>;
  onDismiss: (nudgeId: number) => void;
  onViewConversation: (nudge: CoPilotNudge) => void;
}

const PotentialTimedCommitmentCard: React.FC<PotentialTimedCommitmentCardProps> = ({
  nudge,
  onConfirm,
  onDismiss,
  onViewConversation,
}) => {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const suggestedPayload = nudge.ai_suggestion_payload as PotentialEventPayload | null;

  const getInitialDateTimeStringForInput = () => {
    if (suggestedPayload?.parsed_datetime_utc_suggestion) {
      try {
        const d = new Date(suggestedPayload.parsed_datetime_utc_suggestion);
        // Convert UTC suggestion to user's local time for the datetime-local input
        const localDate = new Date(d.getTime() - (d.getTimezoneOffset() * 60000));
        return localDate.toISOString().slice(0, 16); // YYYY-MM-DDTHH:mm
      } catch (e) { 
        console.error("Error parsing suggested datetime for input:", e); 
      }
    }
    const defaultDate = new Date();
    let daysToAdd = 1;
    const currentDay = defaultDate.getDay();
    if (currentDay === 5) daysToAdd = 3; 
    else if (currentDay === 6) daysToAdd = 2;
    defaultDate.setDate(defaultDate.getDate() + daysToAdd);
    defaultDate.setHours(10, 0, 0, 0);
    return defaultDate.toISOString().slice(0,16); // Fallback correctly formatted
  };
  
  const [eventDatetime, setEventDatetime] = useState<string>(getInitialDateTimeStringForInput());
  const [eventPurpose, setEventPurpose] = useState<string>(
    suggestedPayload?.parsed_purpose_suggestion ||
    (nudge.message_snippet ? `Re: "${nudge.message_snippet.substring(0, 30)}..."` : 'Follow-up')
  );

  // Default to NOT editing if AI has a strong suggestion for date/time AND purpose.
  // Otherwise, start in edit mode so the user can immediately fill details.
  const hasStrongAISuggestions = !!(suggestedPayload?.parsed_datetime_utc_suggestion && suggestedPayload?.parsed_purpose_suggestion);
  const [isEditing, setIsEditing] = useState(!hasStrongAISuggestions); 


  const handleConfirm = async () => {
    if (!eventDatetime || !eventPurpose.trim()) {
      setError("Date/Time and Purpose are required.");
      return;
    }
    setError(null); setIsLoading(true);
    try {
      const localDate = new Date(eventDatetime); 
      if (isNaN(localDate.getTime())) throw new Error("Invalid Date/Time selected.");
      await onConfirm(nudge.id, localDate.toISOString(), eventPurpose.trim());
      // setIsEditing(false); // Collapse on successful confirm - parent will likely remove it
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to confirm. Please try again.");
      console.error("Error in handleConfirm:", err);
    } finally { setIsLoading(false); }
  };
  
  const detectedDateTimeInfo = [
    suggestedPayload?.raw_detected_date_phrase && `Date: "${suggestedPayload.raw_detected_date_phrase}"`,
    suggestedPayload?.raw_detected_time_phrase && `Time: "${suggestedPayload.raw_detected_time_phrase}"`
  ].filter(Boolean).join(' | ');

  // Short AI note for summary view
  const summaryAINote = nudge.ai_suggestion && nudge.ai_suggestion !== "This customer mentioned scheduling or a specific time. Would you like to create a Targeted Event (like an appointment or call)?" 
    ? (nudge.ai_suggestion.length > 60 ? nudge.ai_suggestion.substring(0,57) + "..." : nudge.ai_suggestion)
    : detectedDateTimeInfo ? `AI detected: ${detectedDateTimeInfo}` : "Review this potential event.";


  return (
    <div className={`bg-slate-800/90 border ${isEditing ? 'border-sky-400 shadow-md shadow-sky-500/20' : 'border-sky-500/50'} bg-gradient-to-br from-slate-800/80 to-sky-900/20 rounded-xl p-3 sm:p-4 shadow-lg flex flex-col h-full backdrop-blur-sm transition-all hover:shadow-sky-500/10`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center">
          <CalendarClockIcon className="w-5 h-5 sm:w-6 sm:h-6 mr-2 flex-shrink-0 text-sky-400" />
          <h3 className="text-base sm:text-md font-semibold text-slate-100 truncate">
            Potential Event
            {nudge.customer_name && <span className="text-xs text-slate-400 font-normal ml-1.5">with {nudge.customer_name}</span>}
          </h3>
        </div>
         <button
            onClick={() => setIsEditing(!isEditing)}
            className="p-1.5 text-slate-400 hover:text-sky-300 transition-colors rounded-md hover:bg-slate-700/50"
            title={isEditing ? "View Summary" : "Edit Details"}
          >
            {isEditing ? <ChevronUpIcon className="w-4 h-4 sm:w-5 sm:h-5" /> : <Edit3Icon className="w-4 h-4 sm:w-5 sm:h-5" />}
          </button>
      </div>

      {nudge.message_snippet && (
        <div className="bg-slate-700/50 p-2.5 rounded-md text-slate-200 italic mb-3 text-xs sm:text-sm max-h-24 overflow-y-auto scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-slate-700/30">
          Customer: "{nudge.message_snippet}"
        </div>
      )}
      
      {/* NON-EDITING (SUMMARY) VIEW */}
      {!isEditing && (
        <div className="mb-3 space-y-1.5 text-xs sm:text-sm flex-grow py-2">
          <p className="text-slate-200 flex items-start">
            <strong className="font-medium text-sky-300/90 w-[80px] inline-block flex-shrink-0">Proposed:</strong> 
            <span className="ml-1 flex-1 break-words">{eventDatetime ? `${new Date(eventDatetime).toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })}, ${new Date(eventDatetime).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })} (Local)` : <span className="text-slate-400 italic">Set Date/Time</span>}</span>
          </p>
          <p className="text-slate-200 flex items-start">
            <strong className="font-medium text-sky-300/90 w-[80px] inline-block flex-shrink-0">For:</strong> 
            <span className="ml-1 flex-1 break-words">{eventPurpose || <span className="text-slate-400 italic">Set Purpose</span>}</span>
          </p>
          <p className="text-slate-400 text-[11px] italic mt-2 pt-1.5 border-t border-slate-700/30">
            {summaryAINote}
          </p>
        </div>
      )}

      {/* EDITING VIEW */}
      {isEditing && (
        <div className="transition-all duration-300 ease-in-out flex-grow pt-1">
          {nudge.ai_suggestion && (
            <div className="text-xs text-sky-200/90 mb-2 flex items-start p-2 bg-sky-900/20 rounded-md border border-sky-800/50">
              <InfoIcon className="w-3.5 h-3.5 mr-1.5 mt-0.5 flex-shrink-0 text-sky-300/80" />
              <span>{nudge.ai_suggestion}</span>
            </div>
          )}
          {detectedDateTimeInfo && ( // Only show if there are raw detected phrases
            <div className="mb-2 text-xs text-slate-400 p-1.5 rounded-sm bg-slate-700/30">
              AI detected raw phrases: {detectedDateTimeInfo}
            </div>
          )}
          <div className="space-y-3 mb-3">
            <div>
              <label htmlFor={`event-datetime-${nudge.id}`} className="block text-xs font-medium text-slate-300 mb-1">
                Event Date & Time (Your Local)
              </label>
              <input
                type="datetime-local"
                id={`event-datetime-${nudge.id}`}
                value={eventDatetime}
                onChange={(e) => setEventDatetime(e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 text-slate-200 text-sm rounded-md p-2 focus:ring-1 focus:ring-sky-500 focus:border-sky-500 disabled:opacity-70"
                disabled={isLoading}
              />
            </div>
            <div>
              <label htmlFor={`event-purpose-${nudge.id}`} className="block text-xs font-medium text-slate-300 mb-1">
                Event Purpose
              </label>
              <input
                type="text"
                id={`event-purpose-${nudge.id}`}
                value={eventPurpose}
                onChange={(e) => setEventPurpose(e.target.value)}
                placeholder="E.g., Consultation, Demo Call"
                className="w-full bg-slate-700 border border-slate-600 text-slate-200 text-sm rounded-md p-2 focus:ring-1 focus:ring-sky-500 focus:border-sky-500 disabled:opacity-70"
                disabled={isLoading}
              />
            </div>
          </div>
           {error && (
            <p className="text-xs text-red-400 mb-2 flex items-center">
              <AlertTriangleIcon className="w-4 h-4 mr-1 flex-shrink-0" /> {error}
            </p>
          )}
        </div>
      )}
      
      <div className="mt-auto pt-3 border-t border-slate-700/50 space-y-2">
        <button
          onClick={handleConfirm}
          disabled={isLoading || !eventDatetime || !eventPurpose.trim()}
          className="w-full flex justify-center items-center px-3 py-2.5 border border-transparent text-sm font-semibold rounded-md shadow-sm text-white bg-sky-500 hover:bg-sky-600 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-sky-400 focus:ring-offset-slate-800 disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {isLoading ? <Loader2 className="w-5 h-5 animate-spin mr-2"/> : <CheckCircle2Icon className="w-5 h-5 mr-2"/>}
          Confirm & Notify
        </button>
        <div className="flex space-x-2">
            <button
              onClick={() => onViewConversation(nudge)}
              disabled={isLoading}
              className="flex-1 flex justify-center items-center px-3 py-1.5 border border-slate-600 hover:border-slate-500 text-xs font-medium rounded-md text-slate-300 hover:text-sky-300 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-slate-500 focus:ring-offset-slate-800 disabled:opacity-60"
            >
              <MessageSquareTextIcon className="w-3.5 h-3.5 mr-1.5" /> View Chat
            </button>
            <button
              onClick={() => onDismiss(nudge.id)}
              disabled={isLoading}
              title="Dismiss this suggestion"
              className="flex-1 sm:flex-none flex justify-center items-center sm:px-3 py-1.5 border border-slate-600 hover:border-slate-500 text-xs font-medium rounded-md text-slate-400 hover:text-red-400 focus:outline-none disabled:opacity-60"
            >
              <XIcon className="w-3.5 h-3.5 mr-1.5" /> Dismiss
            </button>
        </div>
      </div>
       <p className="text-right text-[10px] text-slate-500 mt-2">
         Nudge ID: {nudge.id} | {new Date(nudge.created_at).toLocaleDateString()}
       </p>
    </div>
  );
};

export default PotentialTimedCommitmentCard;
