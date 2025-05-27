// frontend/src/components/AppointmentNudgeAssistCard.tsx
"use client";

import React from "react";
import {
  Button
} from "@/components/ui/button"; // Assuming Button is in your ui library
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  CardFooter
} from "@/components/ui/card"; // Assuming Card components
import {
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  ThumbsUp,
  Edit3,
  MessageCircle,
  XCircle,
  ThumbsDown,
  Clock,
  CalendarCheck2,
  Send,
  Zap
} from "lucide-react";
import {
  format,
  parseISO
} from 'date-fns'; // For formatting slot_utc

// Interfaces (should match or be compatible with those in page.tsx)
interface AppointmentRequest {
  id: number;
  original_message_text: string | null;
  parsed_requested_time_text: string | null;
  // Add other relevant fields from AppointmentRequest if needed by the card
}

interface AiSuggestedSlot {
  slot_utc: string; // ISO datetime string from backend
  status_message: string; // e.g., "Slot is available." or "Slot appears open (Flexible Coordinator style, owner to confirm)."
}

interface AppointmentNudgeAssistCardProps {
  actionableAppointment: AppointmentRequest | null; // Make it nullable initially
  aiSuggestedSlots: AiSuggestedSlot[];
  isLoadingSuggestions: boolean;
  suggestionsError: string | null;
  currentCustomerName?: string | null;
  businessTimezone?: string | null; // For displaying times in business local TZ

  // Handler functions to be implemented in page.tsx
  // These handlers will likely trigger state changes in page.tsx to show SMS draft UI etc.
  onConfirmAndDraft: (slot: AiSuggestedSlot) => void;
  onOfferAlternativeAndDraft: (slot: AiSuggestedSlot) => void;
  onDeclineAndDraft: () => void;
  onReplyManuallyOrSuggestOther: () => void; // Could open a more detailed modal or input in page.tsx
  onRetryFetchSuggestions?: () => void; // Optional: if you want a retry button on error
}

const formatSlotInBusinessTimezone = (slotUtc: string, timezone: string | undefined): string => {
  if (!slotUtc) return "N/A";
  try {
    const date = parseISO(slotUtc);
    // date-fns-tz would be ideal here for proper timezone formatting.
    // Using basic date-fns format for now, which will use browser's local time if TZ not handled.
    // For accurate business timezone display, a library like date-fns-tz or manual offset calculation is needed.
    // This is a simplified version.
    const options: Intl.DateTimeFormatOptions = {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    };
    if (timezone) {
      try {
        // This basic approach might not be fully accurate for all timezones/DST with just date-fns
        // return format(date, "eee, MMM d 'at' p", { locale: /* pass business locale if needed */ });
         return new Intl.DateTimeFormat('en-US', {...options, timeZone: timezone }).format(date);
      } catch (e) {
        // Fallback if timezone string is invalid for Intl.DateTimeFormat
        console.warn("Invalid timezone for Intl.DateTimeFormat, falling back:", timezone, e);
        return format(date, "eee, MMM d 'at' p");
      }
    }
    return format(date, "eee, MMM d 'at' p"); // Fallback to browser local time
  } catch (error) {
    console.error("Error formatting date:", error);
    return "Invalid Date";
  }
};


export const AppointmentNudgeAssistCard: React.FC<AppointmentNudgeAssistCardProps> = ({
  actionableAppointment,
  aiSuggestedSlots,
  isLoadingSuggestions,
  suggestionsError,
  currentCustomerName,
  businessTimezone,
  onConfirmAndDraft,
  onOfferAlternativeAndDraft,
  onDeclineAndDraft,
  onReplyManuallyOrSuggestOther,
  onRetryFetchSuggestions
}) => {
  if (!actionableAppointment) {
    // This card should only be rendered if there's an actionable appointment.
    // Handling this case defensively.
    return null;
  }

  const customerRequestDisplay = actionableAppointment.parsed_requested_time_text || actionableAppointment.original_message_text || "their recent request";

  return (
    <Card className="w-full bg-slate-800 border-slate-700 text-white shadow-xl mb-4">
      <CardHeader className="pb-3">
        <CardTitle className="text-lg flex items-center text-sky-400">
          <Zap size={20} className="mr-2" /> AI Nudge Assist
        </CardTitle>
        <CardDescription className="text-slate-400 text-xs">
          For: <span className="font-semibold text-slate-300">{currentCustomerName || "Customer"}</span>
          <br/>
          Regarding their request for: <span className="font-semibold text-slate-300">{customerRequestDisplay}</span>
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {isLoadingSuggestions && (
          <div className="flex items-center justify-center p-4 text-slate-400">
            <RefreshCw size={18} className="mr-2 animate-spin" />
            <span>Finding best slots...</span>
          </div>
        )}

        {!isLoadingSuggestions && suggestionsError && (
          <div className="p-3 bg-red-900/50 border border-red-700/60 rounded-md text-red-300 text-sm">
            <div className="flex items-center">
              <AlertTriangle size={18} className="mr-2" />
              <p>Error: {suggestionsError}</p>
            </div>
            {onRetryFetchSuggestions && (
                 <Button variant="ghost" size="sm" onClick={onRetryFetchSuggestions} className="text-red-300 hover:text-red-200 pl-0 mt-1">
                    Try again
                 </Button>
            )}
          </div>
        )}

        {!isLoadingSuggestions && !suggestionsError && aiSuggestedSlots.length > 0 && (
          <div className="space-y-3">
            <p className="text-sm text-slate-300 font-medium">Here are some suggested times:</p>
            {aiSuggestedSlots.map((slot, index) => (
              <div key={slot.slot_utc + index} className="p-3 bg-slate-700/70 rounded-md border border-slate-600">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between">
                  <div className="mb-2 sm:mb-0">
                    <p className="font-semibold text-slate-100 flex items-center">
                      <CalendarCheck2 size={16} className="mr-2 text-green-400" />
                      {formatSlotInBusinessTimezone(slot.slot_utc, businessTimezone || undefined)}
                    </p>
                    <p className="text-xs text-slate-400 ml-6">{slot.status_message}</p>
                  </div>
                  <div className="flex flex-col sm:flex-row gap-2 sm:items-center shrink-0">
                    {index === 0 ? ( // Primary action for the first (best) suggestion
                      <Button 
                        size="sm" 
                        onClick={() => onConfirmAndDraft(slot)}
                        className="bg-green-600 hover:bg-green-700 text-white w-full sm:w-auto"
                      >
                        <ThumbsUp size={14} className="mr-1.5" /> Confirm & Draft
                      </Button>
                    ) : (
                      <Button 
                        size="sm" 
                        variant="secondary"
                        onClick={() => onOfferAlternativeAndDraft(slot)}
                        className="border-sky-500 text-sky-400 hover:bg-sky-500/20 hover:text-sky-300 w-full sm:w-auto"
                      >
                        <Send size={14} className="mr-1.5" /> Offer this Slot
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {!isLoadingSuggestions && !suggestionsError && aiSuggestedSlots.length === 0 && (
          <p className="text-sm text-slate-400 text-center py-3">
            No specific AI slot suggestions available right now. You can reply manually.
          </p>
        )}
      </CardContent>

      <CardFooter className="flex flex-col sm:flex-row justify-end gap-2 pt-4 border-t border-slate-700">
         <Button variant="secondary" onClick={onReplyManuallyOrSuggestOther} size="sm" className="w-full sm:w-auto border-slate-600 hover:bg-slate-700">
            <Edit3 size={14} className="mr-1.5" /> Reply Manually / Other Time
        </Button>
        <Button variant="destructive" onClick={onDeclineAndDraft} size="sm" className="w-full sm:w-auto bg-red-700/80 hover:bg-red-700">
            <ThumbsDown size={14} className="mr-1.5" /> Decline & Draft Reply
        </Button>
      </CardFooter>
    </Card>
  );
};