// frontend/src/components/SentimentSpotlightCard.tsx
'use client';

import React from 'react';
import { StarIcon, AlertTriangleIcon } from 'lucide-react';

export interface CoPilotNudge {
  id: number;
  business_id: number;
  customer_id?: number | null;
  customer_name?: string | null;
  nudge_type: string;
  status: string;
  message_snippet?: string | null;
  ai_suggestion?: string | null;
  ai_evidence_snippet?: Record<string, any> | null;
  ai_suggestion_payload?: Record<string, any> | null;
  created_at: string;
  updated_at: string;
}

interface SentimentSpotlightCardProps {
  nudge: CoPilotNudge;
  onDismiss: (nudgeId: number) => void;
  onRequestReview?: (nudge: CoPilotNudge) => void;
  onViewConversation: (nudge: CoPilotNudge) => void;
  onPrimaryAction?: (nudge: CoPilotNudge) => void; // For future flexibility
  primaryActionText?: string; // For future flexibility
}

const SentimentSpotlightCard: React.FC<SentimentSpotlightCardProps> = ({
  nudge,
  onDismiss,
  onRequestReview,
  onViewConversation,
  onPrimaryAction,
  primaryActionText
}) => {
  const isPositive = nudge.nudge_type === 'sentiment_positive';
  const isNegative = nudge.nudge_type === 'sentiment_negative'; // Added check for negative

  // Card border color directly reflects sentiment
  const cardBorderColor = isPositive
    ? 'border-yellow-500/60'
    : isNegative
    ? 'border-red-500/60' // Negative sentiment border
    : 'border-slate-600/50';
  const cardAccentBg = isPositive
    ? 'bg-yellow-500/10'
    : isNegative
    ? 'bg-red-500/10' // Negative sentiment background
    : 'bg-slate-700/20';

  const IconComponent = isPositive
    ? StarIcon
    : isNegative
    ? AlertTriangleIcon // Icon for negative sentiment
    : StarIcon; // Default icon
  const iconColor = isPositive
    ? 'text-yellow-400'
    : isNegative
    ? 'text-red-400' // Icon color for negative
    : 'text-slate-400';

  const title = isPositive
    ? `Positive Sentiment`
    : isNegative
    ? `Negative Sentiment` // Title for negative sentiment
    : `Sentiment Insight`;

  // Primary button styling
  const primaryButtonStyles = isPositive
    ? 'bg-purple-600 hover:bg-purple-700 text-white focus:ring-purple-600'
    : isNegative // For negative, a different style or no primary action shown via logic below
    ? 'bg-orange-500 hover:bg-orange-600 text-white focus:ring-orange-500' // Example: an "Address" button style
    : 'bg-slate-600 hover:bg-slate-700 text-white focus:ring-slate-500';

  let currentPrimaryActionHandler = onPrimaryAction;
  let currentPrimaryActionText = primaryActionText;
  let showPrimaryActionButton = !!onPrimaryAction && !!primaryActionText;

  if (isPositive && onRequestReview) {
    currentPrimaryActionHandler = onRequestReview;
    currentPrimaryActionText = "Request Review";
    showPrimaryActionButton = true;
  } else if (isNegative) {
    // For negative sentiment, we might not show a primary "action" button in this iteration,
    // as the main action is "View Chat".
    // If there was a specific primary action for negative, it would be set here.
    // For now, let's assume "View Chat" is sufficient and this primary button might be hidden.
    showPrimaryActionButton = false; // Explicitly hide primary for negative unless defined otherwise
    // If you decide to have a primary action for negative, set it up like this:
    // if (onPrimaryAction) { // A generic onPrimaryAction for negative
    //   currentPrimaryActionHandler = onPrimaryAction;
    //   currentPrimaryActionText = primaryActionText || "Address Concern";
    //   showPrimaryActionButton = true;
    // }
  }


  return (
    <div
      className={`bg-slate-800/80 border ${cardBorderColor} ${cardAccentBg} rounded-lg p-3 sm:p-4 shadow-md flex flex-col h-full backdrop-blur-sm transition-all hover:shadow-lg`}
    >
      {/* Card Header: Icon and Title */}
      <div className="flex items-center mb-2">
        <IconComponent className={`${iconColor} w-5 h-5 sm:w-6 sm:h-6 mr-2 flex-shrink-0`} />
        <h3 className="text-sm sm:text-md font-semibold text-slate-100 truncate" title={title}>
          {title}
          {nudge.customer_name && (
             <span className="text-xs text-slate-400 font-normal ml-1">({nudge.customer_name})</span>
          )}
        </h3>
      </div>

      {/* Message Snippet */}
      <div className="flex-grow mb-2 sm:mb-3 text-xs sm:text-sm">
        {nudge.message_snippet && (
          <div className="bg-slate-700/40 p-2 rounded-md text-slate-300 italic max-h-20 overflow-y-auto scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-slate-700/30">
            "{nudge.message_snippet}"
          </div>
        )}

        {/* Conditional AI Suggestion */}
        {nudge.ai_suggestion && (
          <p className="text-slate-400 mt-2 text-xs">{nudge.ai_suggestion}</p>
        )}
      </div>

      {/* Action Buttons - more compact and responsive */}
      <div className="mt-auto pt-2 sm:pt-3 border-t border-slate-700/50 flex flex-col space-y-2 sm:space-y-0 sm:flex-row sm:space-x-2">
        {showPrimaryActionButton && currentPrimaryActionHandler && currentPrimaryActionText && (
          <button
            onClick={() => currentPrimaryActionHandler(nudge)}
            className={`w-full justify-center items-center px-3 py-1.5 border border-transparent text-xs font-medium rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-slate-800 ${primaryButtonStyles}`}
          >
            {currentPrimaryActionText}
          </button>
        )}
        <button
          onClick={() => onViewConversation(nudge)}
          className="w-full justify-center items-center px-3 py-1.5 border border-slate-600 text-xs font-medium rounded-md text-slate-300 hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-slate-500 focus:ring-offset-slate-800"
        >
          View Chat
        </button>
        <button
          onClick={() => onDismiss(nudge.id)}
          title="Dismiss this suggestion"
          className="w-full sm:w-auto sm:px-2.5 py-1.5 border border-transparent text-xs font-medium rounded-md text-slate-500 hover:text-slate-300 hover:bg-slate-700/50 focus:outline-none"
        >
          Dismiss
        </button>
      </div>
       <p className="text-right text-[10px] text-slate-600 mt-2">
         ID: {nudge.id} | {new Date(nudge.created_at).toLocaleDateString()}
       </p>
    </div>
  );
};

export default SentimentSpotlightCard;