// frontend/src/components/inbox/TimelineItem.tsx
import React, { memo } from 'react';
import { Clock, Check, AlertCircle, Trash2, Edit3, CheckCheck, Star } from 'lucide-react';
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
  onDeleteDraft: (draftId: number | undefined) => void;
  onActionClick: (nudgeId: number, actionType: string) => void;
}

interface AiDraftProps {
  entry: TimelineEntry;
  onEditDraft: (entry: TimelineEntry) => void;
  onDeleteDraft: (draftId: number | undefined) => void;
}

const AiDraft = ({ entry, onEditDraft, onDeleteDraft }: AiDraftProps) => (
  <div className="mt-2 p-3 rounded-lg bg-yellow-500/10 text-yellow-200 text-sm shadow relative border border-yellow-500/30">
    <p className="font-semibold text-xs mb-1 text-yellow-300 opacity-90">AI Draft:</p>
    <p className="whitespace-pre-wrap">{entry.ai_response}</p>
    <div className="flex gap-2 mt-2 justify-end">
      <button onClick={() => onEditDraft(entry)} className="p-1.5 bg-slate-600 hover:bg-slate-500 rounded text-white transition-colors" title="Edit Draft">
        <Edit3 size={14} />
      </button>
      <button onClick={() => onDeleteDraft(entry.ai_draft_id)} className="p-1.5 bg-red-800 hover:bg-red-700 rounded text-white transition-colors" title="Delete Draft">
        <Trash2 size={14} />
      </button>
    </div>
  </div>
);

const TimelineItem = memo(function TimelineItem({ entry, onEditDraft, onDeleteDraft, onActionClick }: TimelineItemProps) {
  const isIncoming = entry.type === "inbound";
  
  return (
    <div
      data-message-id={entry.id}
      // STYLE UPDATE: Refined message bubble colors for better contrast and modern feel.
      className={clsx(
        "p-3 rounded-lg max-w-[80%] break-words text-sm shadow flex flex-col",
        isIncoming ? "self-start bg-slate-700 text-white mr-auto" : "self-end bg-blue-600 text-white ml-auto",
        {
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
          {entry.type === 'outbound' && entry.status === 'delivered' && <CheckCheck className="inline-block w-4 h-4 ml-1 text-green-300" />}
          {entry.type === 'outbound' && (entry.status === 'sent' || entry.status === 'accepted') && <Check className="inline-block w-4 h-4 ml-1 text-gray-300" />}
          {entry.type === 'outbound' && entry.status === 'queued' && <Clock className="inline-block w-3 h-3 ml-1 text-gray-300" />}
          {(entry.type === 'scheduled' || entry.type === 'scheduled_pending') && <Clock className="inline-block w-3 h-3 ml-1" />}
          {entry.type === 'failed_to_send' && <AlertCircle className="inline-block w-3 h-3 ml-1 text-red-300" />}
        </span>
      )}

      {entry.is_faq_answer && <p className="text-xs text-blue-300 mt-1 italic self-start">(Auto-reply: FAQ)</p>}
      {entry.appended_opt_in_prompt && <p className="text-xs text-gray-400 mt-1 italic self-start">(Opt-in prompt included)</p>}
      
      {isIncoming && entry.ai_response && (
        <AiDraft entry={entry} onEditDraft={onEditDraft} onDeleteDraft={onDeleteDraft} />
      )}

      {isIncoming && entry.contextual_action && entry.contextual_action.type === "REQUEST_REVIEW" && (
        <div className="mt-2 p-2 rounded-lg bg-emerald-500/20 text-white text-sm shadow relative border border-emerald-600/30 flex items-center justify-between">
          <p className="font-semibold text-xs mr-2 text-emerald-300">AI Suggestion:</p>
          <p className="flex-1">{entry.contextual_action.ai_suggestion}</p>
          <button
            onClick={() => onActionClick(entry.contextual_action!.nudge_id, "REQUEST_REVIEW")}
            className="ml-3 p-1.5 bg-emerald-700 hover:bg-emerald-800 rounded text-white flex items-center transition-colors"
            title="Request Review"
          >
            <Star size={14} className="mr-1" /> Request Review
          </button>
        </div>
      )}
    </div>
  );
});

export default TimelineItem;