// frontend/src/components/inbox/CustomerListItem.tsx

import React, { memo } from 'react';
import clsx from 'clsx';
import { format, isValid, parseISO } from 'date-fns';
import { Edit3, Star } from 'lucide-react';

const formatDate = (dateString: string | null | undefined): string => {
  if (!dateString) return "";
  const date = parseISO(dateString);
  if (!isValid(date)) return "";
  const now = new Date();
  if (format(date, 'yyyy-MM-dd') === format(now, 'yyyy-MM-dd')) return format(date, "p");
  if (now.getTime() - date.getTime() < 7 * 24 * 60 * 60 * 1000) return format(date, "eee");
  return format(date, "MMM d");
};

// --- FIX: Define the expected props shape directly in this file ---
// This avoids type errors if a central types file is not updated.
interface CustomerListItemProps {
  summary: {
    customer_id: number;
    customer_name: string | null;
    last_message_content: string | null;
    last_message_timestamp: string | null;
    unread_message_count: number;
    has_draft: boolean;
    has_opportunity: boolean;
  };
  isActive: boolean;
  onClick: (customerId: number) => void;
}

const CustomerListItem = memo(function CustomerListItem({ summary, isActive, onClick }: CustomerListItemProps) {
  const isUnread = summary.unread_message_count > 0;
  
  return (
    <button
      onClick={() => onClick(summary.customer_id)}
      className={clsx(
        "w-full text-left p-3 hover:bg-[#242842] transition-colors border-b border-[#2A2F45]",
        isActive ? "bg-[#2A2F45] ring-2 ring-blue-500" : "bg-transparent",
      )}
    >
      <div className="flex justify-between items-start">
        <h3 className={clsx("text-sm text-white truncate", isUnread && !isActive ? "font-semibold" : "font-medium")}>
          {summary.customer_name || "Unknown Customer"}
        </h3>
        <span className={clsx("text-xs whitespace-nowrap", isUnread && !isActive ? "text-blue-400" : "text-gray-400")}>
            {formatDate(summary.last_message_timestamp)}
        </span>
      </div>
      <div className="flex justify-between items-center mt-1">
        <p className={clsx("text-xs truncate", isUnread && !isActive ? "text-gray-200" : "text-gray-400")}>
          {summary.last_message_content || "No recent messages."}
        </p>
        <div className="flex items-center space-x-2">
            {summary.has_opportunity && <Star size={14} className="text-yellow-400" aria-label="Opportunity detected" />}
            {summary.has_draft && <Edit3 size={14} className="text-cyan-400" aria-label="AI Draft pending" />}
            {isUnread && (
                <span className="flex items-center justify-center bg-blue-500 text-white rounded-full text-xs font-bold w-5 h-5">
                    {summary.unread_message_count}
                </span>
            )}
        </div>
      </div>
    </button>
  );
});

export default CustomerListItem;