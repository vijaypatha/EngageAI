import React, { memo } from 'react';
import clsx from 'clsx';
import { format, isValid, parseISO } from 'date-fns';
import { InboxCustomerSummary } from '@/types';

const formatDate = (dateString: string | undefined): string => {
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
  return (
    <button
      onClick={() => onClick(summary.customer_id)}
      className={clsx(
        "w-full text-left p-3 hover:bg-[#242842] transition-colors border-b border-[#2A2F45]",
        isActive ? "bg-[#2A2F45] ring-2 ring-blue-500" : "bg-transparent",
      )}
    >
      <div className="flex justify-between items-center">
        <h3 className={clsx("text-sm text-white truncate", summary.is_unread && !isActive ? "font-semibold" : "font-medium")}>
          {summary.customer_name || "Unknown Customer"}
        </h3>
        <span className={clsx("text-xs whitespace-nowrap ml-2", summary.is_unread && !isActive ? "text-blue-400" : "text-gray-400")}>
          {formatDate(summary.last_message_timestamp)}
        </span>
      </div>
      <p className={clsx("text-xs truncate mt-1", summary.is_unread && !isActive ? "text-gray-200" : "text-gray-400")}>
        {summary.last_message_preview}
      </p>
    </button>
  );
});

export default CustomerListItem;