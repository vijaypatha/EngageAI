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
    className={clsx(
      "flex items-center space-x-2 px-3 py-1.5 text-sm font-medium rounded-full transition-all duration-200",
      isActive
        ? "bg-blue-600 text-white shadow-md"
        : "bg-gray-700 text-gray-300 hover:bg-gray-600 hover:text-white"
    )}
  >
    <Icon size={14} />
    <span>{label}</span>
    <span className={clsx(
        "text-xs font-semibold px-1.5 py-0.5 rounded-full",
        isActive ? "bg-white text-blue-600" : "bg-gray-500 text-gray-200"
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
    <div className="p-3 border-b border-[#2A2F45] bg-[#1A1D2D]">
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