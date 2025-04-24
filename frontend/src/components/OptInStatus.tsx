import { Check, Clock, X, AlertTriangle } from "lucide-react";
import clsx from "clsx";

export type OptInStatus = "opted_in" | "opted_out" | "waiting" | "pending" | "error";

interface OptInStatusBadgeProps {
  status: OptInStatus;
  showIcon?: boolean;
  size?: "sm" | "md";
  lastUpdated?: string | null;
}

export function OptInStatusBadge({ 
  status, 
  showIcon = true,
  size = "md",
  lastUpdated = null
}: OptInStatusBadgeProps) {
  // Validate status
  const validStatus = ["opted_in", "opted_out", "waiting", "pending", "error"].includes(status) 
    ? status 
    : "error";

  const statusConfig = {
    opted_in: {
      label: "Messages On",
      icon: Check,
      className: "bg-emerald-400/10 text-emerald-400 border-emerald-400/20",
      tooltip: lastUpdated ? `Opted in on ${new Date(lastUpdated).toLocaleDateString()}` : undefined
    },
    opted_out: {
      label: "Declined messages",
      icon: X,
      className: "bg-red-400/10 text-red-400 border-red-400/20",
      tooltip: lastUpdated ? `Opted out on ${new Date(lastUpdated).toLocaleDateString()}` : undefined
    },
    waiting: {
      label: "Awaiting first response",
      icon: Clock,
      className: "bg-yellow-400/10 text-yellow-400 border-yellow-400/20",
      tooltip: "Customer has not responded to any messages yet"
    },
    pending: {
      label: "Opt-in message sent",
      icon: Clock,
      className: "bg-blue-400/10 text-blue-400 border-blue-400/20",
      tooltip: "Waiting for customer to opt in or out"
    },
    error: {
      label: "Status unknown",
      icon: AlertTriangle,
      className: "bg-orange-400/10 text-orange-400 border-orange-400/20",
      tooltip: "Could not determine opt-in status"
    }
  };

  const config = statusConfig[validStatus];
  const Icon = config.icon;

  return (
    <div className="relative group">
      <span className={clsx(
        "inline-flex items-center gap-1.5 rounded-full border",
        "font-medium transition-colors",
        size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-sm",
        config.className
      )}>
        {showIcon && <Icon className={size === "sm" ? "w-3 h-3" : "w-4 h-4"} />}
        {config.label}
      </span>
      {config.tooltip && (
        <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-2 py-1 bg-black/90 text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap">
          {config.tooltip}
        </div>
      )}
    </div>
  );
}