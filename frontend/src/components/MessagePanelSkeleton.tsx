// frontend/src/components/MessagePanelSkeleton.tsx
import React from 'react';

const MessageBubbleSkeleton: React.FC<{ alignSelf: 'self-start' | 'self-end' }> = ({ alignSelf }) => {
  return (
    <div className={`p-3 rounded-lg max-w-[70%] break-words text-sm shadow animate-pulse ${alignSelf} flex flex-col`}>
      <div className={`h-4 bg-gray-700 rounded w-full mb-1 ${alignSelf === 'self-start' ? 'mr-auto' : 'ml-auto'}`}></div>
      <div className={`h-3 bg-gray-700 rounded w-3/4 mb-2 ${alignSelf === 'self-start' ? 'mr-auto' : 'ml-auto'}`}></div>
      <div className="h-2 bg-gray-700 rounded w-1/4 self-end opacity-80"></div>
    </div>
  );
};

export const MessagePanelSkeleton: React.FC = () => {
  return (
    <>
      <div className="p-4 bg-[#1A1D2D] border-b border-[#2A2F45] shrink-0 animate-pulse">
        <div className="h-6 bg-gray-700 rounded w-1/2 mb-1"></div>
        <div className="h-3 bg-gray-700 rounded w-1/3"></div>
      </div>
      <div className="flex flex-col flex-1 overflow-y-auto p-4 space-y-3 bg-[#0B0E1C]">
        <MessageBubbleSkeleton alignSelf="self-start" />
        <MessageBubbleSkeleton alignSelf="self-end" />
        <MessageBubbleSkeleton alignSelf="self-start" />
        <MessageBubbleSkeleton alignSelf="self-end" />
        <MessageBubbleSkeleton alignSelf="self-start" />
      </div>
      <div className="p-4 bg-[#1A1D2D] border-t border-[#2A2F45] shrink-0 animate-pulse">
        <div className="flex items-center gap-2">
          <div className="flex-1 h-10 bg-gray-700 rounded-lg"></div>
          <div className="w-10 h-10 bg-gray-700 rounded-lg"></div>
        </div>
      </div>
    </>
  );
};
