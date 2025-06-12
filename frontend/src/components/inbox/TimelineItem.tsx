import React, { memo } from 'react';
import { Clock, Check, AlertCircle, Trash2, Edit3, CheckCheck } from 'lucide-react';
import clsx from 'clsx';
import { format, isValid, parseISO } from 'date-fns';
import { TimelineEntry } from '@/types';

const formatMessageTimestamp = (dateString: string | null | undefined): string => {
  if (!dateString) return "";
  const date = parseISO(dateString);
  return isValid(date) ? format(date, "MMM d, p") : "";
};

interface TimelineItemProps {
  entry: TimelineEntry;
  onEditDraft: (entry: TimelineEntry) => void;
  onDeleteDraft: (id: string | number) => void;
}

const TimelineItem = memo(function TimelineItem({ entry, onEditDraft, onDeleteDraft }: TimelineItemProps) {
  return (
    <div
      data-message-id={entry.id}
      className={clsx(
        "p-3 rounded-lg max-w-[70%] break-words text-sm shadow flex flex-col",
        // Incoming messages (customer, unknown_business_message) should be on the right
        (entry.type === "customer" || entry.type === "unknown_business_message") && "self-end ml-auto",
        // Outgoing messages (sent, ai_draft, scheduled, etc.) should be on the left
        (entry.type === "sent" || entry.type === "outbound_ai_reply" || entry.type === "ai_draft" || entry.type === "scheduled" || entry.type === "scheduled_pending" || entry.type === "failed_to_send") && "self-start mr-auto",
        {
          "bg-[#2A2F45] text-white": entry.type === "customer", // Customer messages background
          "bg-blue-600 text-white": entry.type === "sent" || entry.type === "outbound_ai_reply", // Sent by business/AI background
          "bg-yellow-500 text-black": entry.type === "ai_draft",
          "bg-gray-500 text-white": entry.type === "scheduled" || entry.type === "scheduled_pending",
          "bg-red-700 text-white": entry.type === "failed_to_send",
          "bg-purple-600 text-white": entry.type === "unknown_business_message",
        }
      )}
    >
      <p className="whitespace-pre-wrap">{entry.content}</p>
      {entry.timestamp && (
        <span className="text-xs text-gray-300 mt-1 self-end opacity-80">
          {formatMessageTimestamp(entry.timestamp)}
          {entry.type === 'sent' && entry.status === 'delivered' && <CheckCheck className="inline-block w-4 h-4 ml-1 text-green-300" />}
          {entry.type === 'sent' && (entry.status === 'sent' || entry.status === 'accepted') && <Check className="inline-block w-4 h-4 ml-1 text-gray-300" />}
          {entry.type === 'sent' && entry.status === 'queued' && <Clock className="inline-block w-3 h-3 ml-1 text-gray-300" />}
          {(entry.type === 'scheduled' || entry.type === 'scheduled_pending') && <Clock className="inline-block w-3 h-3 ml-1" />}
          {entry.type === 'failed_to_send' && <AlertCircle className="inline-block w-3 h-3 ml-1 text-red-300" />}
        </span>
      )}
      {entry.is_faq_answer && <p className="text-xs text-blue-300 mt-1 italic self-start">(Auto-reply: FAQ)</p>}
      {entry.appended_opt_in_prompt && <p className="text-xs text-gray-400 mt-1 italic self-start">(Opt-in prompt included)</p>}
      {entry.type === "ai_draft" && (
        <div className="flex gap-2 mt-2 self-end">
          <button onClick={() => onEditDraft(entry)} className="p-1.5 bg-gray-700 hover:bg-gray-600 rounded text-white transition-colors" title="Edit Draft"><Edit3 size={14} /></button>
          <button onClick={() => onDeleteDraft(entry.id)} className="p-1.5 bg-red-800 hover:bg-red-700 rounded text-white transition-colors" title="Delete Draft"><Trash2 size={14} /></button>
        </div>
      )}
    </div>
  );
});

export default TimelineItem;