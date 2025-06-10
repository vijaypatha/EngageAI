// frontend/src/components/CustomerListSkeleton.tsx
import React from 'react';

interface CustomerListSkeletonProps {
  count: number;
}

const CustomerListItemSkeleton: React.FC = () => {
  return (
    <div className="w-full text-left p-3 border-b border-[#2A2F45] animate-pulse">
      <div className="flex justify-between items-center">
        <div className="h-4 bg-gray-700 rounded w-3/4"></div>
        <div className="h-3 bg-gray-700 rounded w-1/4"></div>
      </div>
      <div className="h-3 bg-gray-700 rounded w-5/6 mt-2"></div>
    </div>
  );
};

export const CustomerListSkeleton: React.FC<CustomerListSkeletonProps> = ({ count }) => {
  return (
    <>
      {Array.from({ length: count }).map((_, index) => (
        <CustomerListItemSkeleton key={index} />
      ))}
    </>
  );
};
