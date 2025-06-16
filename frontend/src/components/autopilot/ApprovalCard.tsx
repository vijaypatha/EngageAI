// frontend/src/components/autopilot/ApprovalCard.tsx
"use client";

import { ApprovalQueueItem } from '@/types';
import { X, CalendarPlus, User, Clock, Sparkles } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

interface ApprovalCardProps {
  item: ApprovalQueueItem;
  // This function will now open the scheduling modal by passing the full item
  onSchedule: (item: ApprovalQueueItem) => void;
  onReject: (id: number) => void;
  isProcessing: boolean;
}

export default function ApprovalCard({ item, onSchedule, onReject, isProcessing }: ApprovalCardProps) {
  // Format the campaign type for display (e.g., "REFERRAL_CAMPAIGN" -> "Referral Campaign")
  const campaignType = item.message_metadata?.campaign_type
    ?.replace(/_/g, ' ')
    .replace(/\b\w/g, l => l.toUpperCase()) || 'AI Suggestion';

  return (
    <div className="bg-slate-800/80 border border-slate-700 p-4 rounded-xl shadow-lg flex flex-col gap-4 transition-all duration-300 hover:border-purple-500/50">
      {/* Card Header */}
      <div className="flex justify-between items-start">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-purple-300">
            <Sparkles className="w-4 h-4" />
            <span>{campaignType}</span>
          </div>
          <div className="flex items-center gap-2 mt-1 text-slate-200">
            <User className="w-4 h-4 text-slate-400" />
            <span className="font-bold">{item.customer.customer_name}</span>
          </div>
        </div>
        <div className="text-xs text-slate-500 flex items-center gap-1.5 pt-1">
          <Clock className="w-3 h-3" />
          {formatDistanceToNow(new Date(item.created_at), { addSuffix: true })}
        </div>
      </div>
      
      {/* Message Content */}
      <blockquote className="text-sm text-slate-300 bg-slate-900/70 p-3 rounded-md border border-slate-700/50">
        "{item.content}"
      </blockquote>

      {/* Action Buttons */}
      <div className="flex justify-end items-center gap-3">
        <button
          onClick={() => onReject(item.id)}
          disabled={isProcessing}
          className="px-4 py-2 text-sm font-semibold text-slate-300 bg-slate-700 hover:bg-slate-600 rounded-md flex items-center gap-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <X className="w-4 h-4" /> Reject
        </button>
        <button
          onClick={() => onSchedule(item)}
          disabled={isProcessing}
          className="px-5 py-2 text-sm font-semibold text-white bg-purple-600 hover:bg-purple-700 rounded-md flex items-center gap-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <CalendarPlus className="w-4 h-4" />
          Schedule
        </button>
      </div>
    </div>
  );
}
