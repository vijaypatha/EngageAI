// frontend/src/components/inbox/CustomerListItem.tsx
import React, { memo } from 'react';
import clsx from 'clsx';
import { format, isValid, parseISO } from 'date-fns';
import { Edit3, Star, MessageSquare, Calendar, Lightbulb } from 'lucide-react';

// --- Type Definitions ---
interface ActiveNudge {
  type: string;
  text: string;
}

interface CustomerListItemProps {
  summary: {
    customer_id: number;
    customer_name: string | null;
    last_message_content: string | null;
    last_message_timestamp: string | null;
    unread_message_count: number;
    active_nudges: ActiveNudge[];
  };
  isActive: boolean;
  onClick: (customerId: number) => void;
}

// --- Helper Functions ---
const formatDate = (dateString: string | null | undefined): string => {
  if (!dateString) return "";
  const date = parseISO(dateString);
  if (!isValid(date)) return "";
  const now = new Date();
  const dayDiff = (now.getTime() - date.getTime()) / (1000 * 3600 * 24);
  
  if (dayDiff < 1 && format(date, 'yyyy-MM-dd') === format(now, 'yyyy-MM-dd')) return format(date, "p");
  if (dayDiff < 7) return format(date, "eee");
  return format(date, "MMM d");
};

const nudgeIconMap: { [key: string]: { icon: React.ElementType, color: string } } = {
  draft: { icon: Edit3, color: 'text-cyan-400' },
  sentiment_positive: { icon: Star, color: 'text-yellow-400' },
  potential_targeted_event: { icon: Calendar, color: 'text-fuchsia-400' },
  strategic_engagement_opportunity: { icon: Lightbulb, color: 'text-purple-400' },
  default: { icon: MessageSquare, color: 'text-gray-400' }
};

const NudgeTag: React.FC<{ nudge: ActiveNudge }> = ({ nudge }) => {
  const { icon: Icon, color } = nudgeIconMap[nudge.type] || nudgeIconMap.default;
  return (
    <div className="flex items-center gap-1.5 text-xs text-gray-300">
      <Icon size={12} className={color} />
      <p className="truncate" title={nudge.text}>{nudge.text}</p>
    </div>
  );
};

const CustomerListItem = memo(function CustomerListItem({ summary, isActive, onClick }: CustomerListItemProps) {
  const isUnread = summary.unread_message_count > 0;
  
  return (
    <button
      onClick={() => onClick(summary.customer_id)}
      // STYLE UPDATE: Refined active and hover states for better visual feedback.
      className={clsx(
        "w-full text-left p-3 transition-colors border-b border-slate-700/50",
        isActive ? "bg-blue-900/50" : "bg-transparent hover:bg-slate-800/60",
      )}
    >
      <div className="flex justify-between items-start gap-3">
        <h3 className={clsx("text-sm text-white truncate", isUnread && !isActive ? "font-semibold" : "font-medium")}>
          {summary.customer_name || "Unknown Customer"}
        </h3>
        <span className={clsx("text-xs whitespace-nowrap", isUnread && !isActive ? "text-blue-400 font-semibold" : "text-gray-400")}>
            {formatDate(summary.last_message_timestamp)}
        </span>
      </div>

      <div className="flex justify-between items-center mt-1.5">
        <div className="flex-1 min-w-0">
          <p className={clsx("text-xs truncate", isUnread && !isActive ? "text-gray-200" : "text-gray-400")}>
            {summary.last_message_content || "No recent messages."}
          </p>
          
          {summary.active_nudges && summary.active_nudges.length > 0 && (
            <div className="mt-1.5 space-y-1">
              {summary.active_nudges.map((nudge, index) => (
                <NudgeTag key={index} nudge={nudge} />
              ))}
            </div>
          )}
        </div>

        {isUnread && (
            <span className="flex items-center justify-center bg-blue-500 text-white rounded-full text-xs font-bold w-5 h-5 ml-2 shrink-0">
                {summary.unread_message_count}
            </span>
        )}
      </div>
    </button>
  );
});

export default CustomerListItem;