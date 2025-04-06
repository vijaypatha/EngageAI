import React from "react";

export default function StatItem({
  label,
  value,
  icon,
  tooltip,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  tooltip: string;
}) {
  return (
    <div className="flex items-center gap-2 cursor-default">
      {icon}
      <div className="flex flex-col">
        <span className="text-xs text-zinc-400">{label}</span>
        <span className="text-xl font-bold">{value}</span>
      </div>
    </div>
  );
}
