import { Check, Clock, X } from "lucide-react";
import clsx from "clsx";

export type OptInStatus = "opted_in" | "opted_out" | "waiting" | "pending";

interface OptInStatusBadgeProps {
  status: OptInStatus;
  showIcon?: boolean;
  size?: "sm" | "md";
}

export function OptInStatusBadge({ 
  status, 
  showIcon = true,
  size = "md" 
}: OptInStatusBadgeProps) {
  const statusConfig = {
    opted_in: {
      label: "Messages On",
      icon: Check,
      className: "bg-emerald-400/10 text-emerald-400 border-emerald-400/20"
    },
    opted_out: {
      label: "Declined messages",
      icon: X,
      className: "bg-red-400/10 text-red-400 border-red-400/20"
    },
    waiting: {
      label: "Awaiting first response",
      icon: Clock,
      className: "bg-yellow-400/10 text-yellow-400 border-yellow-400/20"
    },
    pending: {
      label: "Opt-in message sent",
      icon: Clock,
      className: "bg-blue-400/10 text-blue-400 border-blue-400/20"
    }
  };

  const config = statusConfig[status];
  const Icon = config.icon;

  return (
    <span className={clsx(
      "inline-flex items-center gap-1.5 rounded-full border",
      "font-medium transition-colors",
      size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-sm",
      config.className
    )}>
      {showIcon && <Icon className={size === "sm" ? "w-3 h-3" : "w-4 h-4"} />}
      {config.label}
    </span>
  );
}