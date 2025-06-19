// frontend/src/components/inbox/InboxFilterBar.tsx
import React from 'react';
import { MessageSquare, Edit3, Star, Inbox } from 'lucide-react';
import clsx from 'clsx';

export type InboxFilterType = 'all' | 'unread' | 'drafts' | 'opportunities';

interface FilterPillProps {
  icon: React.ElementType;
  label: string;
  count: number;
  isActive: boolean;
  onClick: () => void;
}

const FilterPill: React.FC<FilterPillProps> = ({ icon: Icon, label, count, isActive, onClick }) => (
  <button
    onClick={onClick}
    // STYLE UPDATE: Changed colors for a more integrated, modern feel.
    className={clsx(
      "flex items-center space-x-2 px-3 py-1.5 text-sm font-medium rounded-full transition-all duration-200",
      isActive
        ? "bg-blue-600 text-white"
        : "bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white"
    )}
  >
    <Icon size={14} />
    <span>{label}</span>
    {/* STYLE UPDATE: Updated count badge colors. */}
    <span className={clsx(
        "text-xs font-semibold px-1.5 py-0.5 rounded-full",
        isActive ? "bg-white text-blue-600" : "bg-slate-600 text-slate-200"
    )}>
        {count}
    </span>
  </button>
);


interface InboxFilterBarProps {
  stats: {
    unread: number;
    drafts: number;
    opportunities: number;
  };
  activeFilter: InboxFilterType;
  onFilterChange: (filter: InboxFilterType) => void;
  totalConversations: number;
}

export default function InboxFilterBar({ stats, activeFilter, onFilterChange, totalConversations }: InboxFilterBarProps) {
  return (
    // STYLE UPDATE: Changed background and border to match new theme.
    <div className="p-3 border-b border-slate-700 bg-slate-800 overflow-x-auto flex-shrink-0 aai-scrollbars-dark">
        <div className="flex items-center space-x-2">
             <FilterPill
                icon={Inbox}
                label="All"
                count={totalConversations}
                isActive={activeFilter === 'all'}
                onClick={() => onFilterChange('all')}
            />
            <FilterPill
                icon={MessageSquare}
                label="Unread"
                count={stats.unread}
                isActive={activeFilter === 'unread'}
                onClick={() => onFilterChange('unread')}
            />
             <FilterPill
                icon={Edit3}
                label="Drafts"
                count={stats.drafts}
                isActive={activeFilter === 'drafts'}
                onClick={() => onFilterChange('drafts')}
            />
            <FilterPill
                icon={Star}
                label="Opportunities"
                count={stats.opportunities}
                isActive={activeFilter === 'opportunities'}
                onClick={() => onFilterChange('opportunities')}
            />
        </div>
    </div>
  );
}