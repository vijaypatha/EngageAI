import React from 'react';

const Skeleton = ({ className }: { className?: string }) => (
  <div className={`bg-[#2A2F45] animate-pulse rounded-md ${className}`} />
);

const CustomerListSkeleton = () => (
  <div className="p-2 space-y-2">
    {Array.from({ length: 12 }).map((_, i) => (
      <div key={i} className="flex items-center space-x-3 p-2">
        <div className="flex-1 space-y-2 py-1">
          <div className="flex justify-between items-center">
            <Skeleton className="h-4 w-3/5" />
            <Skeleton className="h-3 w-1/5" />
          </div>
          <Skeleton className="h-3 w-4/5" />
        </div>
      </div>
    ))}
  </div>
);

const ChatViewSkeleton = () => (
  <div className="p-4 space-y-4">
    <div className="flex flex-col items-start"><Skeleton className="h-16 w-1/2" /></div>
    <div className="flex flex-col items-end"><Skeleton className="h-20 w-3/5" /></div>
    <div className="flex flex-col items-start"><Skeleton className="h-12 w-2/5" /></div>
  </div>
);

export const InboxSkeleton = () => (
  <div className="h-screen flex md:flex-row flex-col bg-[#0B0E1C]">
    <aside className="hidden md:flex flex-col w-80 bg-[#1A1D2D] border-r border-[#2A2F45] h-full overflow-y-auto">
      <div className="p-4 border-b border-[#2A2F45] shrink-0"><Skeleton className="h-6 w-1/3" /></div>
      <CustomerListSkeleton />
    </aside>
    <main className="flex-1 flex flex-col bg-[#0F1221] h-full">
      <div className="p-4 bg-[#1A1D2D] border-b border-[#2A2F45] shrink-0 space-y-2">
        <Skeleton className="h-6 w-1/4" /><Skeleton className="h-4 w-1/2" />
      </div>
      <div className="flex-1 overflow-y-auto"><ChatViewSkeleton /></div>
      <div className="p-4 bg-[#1A1D2D] border-t border-[#2A2F45] shrink-0"><Skeleton className="h-10 w-full" /></div>
    </main>
  </div>
);