// frontend/src/components/inbox/CustomerListItem.tsx

import React, { memo } from 'react';
import clsx from 'clsx';
import { format, isValid, parseISO } from 'date-fns';
import { InboxCustomerSummary } from '@/types';
import { Circle } from 'lucide-react'; // Added Circle icon

const formatDate = (dateString: string | null | undefined): string => { // Changed type to allow null
  if (!dateString) return "";
  const date = parseISO(dateString);
  if (!isValid(date)) return "";
  const now = new Date();
  if (format(date, 'yyyy-MM-dd') === format(now, 'yyyy-MM-dd')) return format(date, "p");
  if (now.getTime() - date.getTime() < 7 * 24 * 60 * 60 * 1000) return format(date, "eee");
  return format(date, "MMM d");
};

interface CustomerListItemProps {
  summary: InboxCustomerSummary;
  isActive: boolean;
  onClick: (customerId: number) => void;
}

const CustomerListItem = memo(function CustomerListItem({ summary, isActive, onClick }: CustomerListItemProps) {
  const isUnread = summary.unread_message_count > 0; // Derive isUnread from count
  
  return (
    <button
      onClick={() => onClick(summary.customer_id)}
      className={clsx(
        "w-full text-left p-3 hover:bg-[#242842] transition-colors border-b border-[#2A2F45]",
        isActive ? "bg-[#2A2F45] ring-2 ring-blue-500" : "bg-transparent",
      )}
    >
      <div className="flex justify-between items-center">
        <h3 className={clsx("text-sm text-white truncate", isUnread && !isActive ? "font-semibold" : "font-medium")}>
          {summary.customer_name || "Unknown Customer"}
        </h3>
        <div className="flex items-center"> {/* Wrap date and unread indicator */}
          <span className={clsx("text-xs whitespace-nowrap", isUnread && !isActive ? "text-blue-400" : "text-gray-400")}>
            {formatDate(summary.last_message_timestamp)}
          </span>
          {isUnread && !isActive && ( // Conditionally render unread indicator
            <span className="ml-2 flex items-center justify-center bg-blue-500 text-white rounded-full text-xs font-bold w-5 h-5">
              {summary.unread_message_count}
            </span>
          )}
        </div>
      </div>
      <p className={clsx("text-xs truncate mt-1", isUnread && !isActive ? "text-gray-200" : "text-gray-400")}>
        {summary.last_message_content || "No recent messages."} {/* Use last_message_content */}
      </p>
    </button>
  );
});

export default CustomerListItem;