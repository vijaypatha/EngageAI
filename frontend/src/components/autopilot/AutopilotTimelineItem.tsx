// frontend/src/components/autopilot/AutopilotTimelineItem.tsx
"use client";

import React, { memo } from 'react';
import { Clock, Check, AlertCircle, Trash2, Edit3, CheckCheck, Star, CalendarDays, Undo2 } from 'lucide-react';
import clsx from 'clsx';
import { format, isValid, parseISO } from 'date-fns';
import { TimelineEntry } from '@/types'; // Still relies on TimelineEntry structure

const formatMessageTimestamp = (dateString: string | null | undefined): string => {
  if (!dateString) return "";
  const date = parseISO(dateString);
  return isValid(date) ? format(date, "MMM d, p") : "";
};

interface AutopilotTimelineItemProps {
  entry: TimelineEntry; // Autopilot messages will be mapped to TimelineEntry format
  onActionClick: (messageId: number, actionType: string) => void; // Specific to Autopilot actions
  // Removed onEditDraft and onDeleteDraft as these are specific to Inbox AI drafts and not directly relevant here.
}

const AutopilotTimelineItem = memo(function AutopilotTimelineItem({ entry, onActionClick }: AutopilotTimelineItemProps) {
  // For Autopilot messages, they are always "outgoing" from the business perspective (scheduled outbound)
  const isOutgoing = true; // All messages in Autopilot Plan are scheduled outbound messages

  return (
    <div
      data-message-id={entry.id}
      className={clsx(
        "p-3 rounded-lg max-w-[70%] break-words text-sm shadow flex flex-col",
        // Autopilot messages are always self-end (right-aligned) as they are outgoing
        "self-end ml-auto",
        {
          // Specific styling for scheduled messages in Autopilot Plan
          "bg-purple-600 text-white": entry.type === "scheduled", 
          "bg-red-700 text-white": entry.type === "failed_to_send", // In case a scheduled message failed
          "bg-purple-600/50 text-white": entry.type === "unknown_business_message", // Fallback, less likely here
          // Removed inbound/outbound/outbound_ai_reply specific styles from original TimelineItem
          // as this component is specifically for 'scheduled' type in Autopilot context.
        }
      )}
    >
      <p className="whitespace-pre-wrap">{entry.content}</p>
      
      {entry.timestamp && (
        <span className="text-xs text-gray-300 mt-1 self-end opacity-80">
          {formatMessageTimestamp(entry.timestamp)}
          {/* Using specific icon for scheduled messages */}
          {entry.type === 'scheduled' && <CalendarDays className="inline-block w-3 h-3 ml-1" />}
          {entry.type === 'failed_to_send' && <AlertCircle className="inline-block w-3 h-3 ml-1 text-red-300" />}
        </span>
      )}

      {/* Removed is_faq_answer and appended_opt_in_prompt as they are not relevant for Autopilot messages */}
      
      {/* Autopilot Message Actions: Edit & Cancel */}
      {entry.type === 'scheduled' && entry.contextual_action && entry.contextual_action.type === "AUTOPILOT_MESSAGE_ACTIONS" && (
        <div className="mt-2 p-2 rounded-lg bg-purple-700/50 text-white text-sm shadow relative border border-purple-600/70 flex items-center justify-between">
            <p className="font-semibold text-xs mr-2">Manage Scheduled Message:</p>
            <div className="flex gap-2">
                <button 
                    onClick={() => onActionClick(entry.id as number, "EDIT_AUTOPILOT_MESSAGE")} // Pass message ID and specific action type
                    className="p-1.5 bg-purple-800 hover:bg-purple-900 rounded text-white transition-colors" 
                    title="Edit Message"
                >
                    <Edit3 size={14} />
                </button>
                <button 
                    onClick={() => onActionClick(entry.id as number, "DELETE_AUTOPILOT_MESSAGE")} // Pass message ID and specific action type
                    className="p-1.5 bg-red-800 hover:bg-red-900 rounded text-white transition-colors" 
                    title="Cancel Message"
                >
                    <Trash2 size={14} />
                </button>
            </div>
        </div>
      )}
    </div>
  );
});

export default AutopilotTimelineItem;