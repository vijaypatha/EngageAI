// components/GrowthOpportunityCard.tsx
'use client';

import React, { useState } from 'react';
import { CoPilotNudge } from './SentimentSpotlightCard';
import { TrendingUpIcon, UsersIcon, Loader2, ArrowRight } from 'lucide-react';

interface GrowthOpportunityCardProps {
  nudge: CoPilotNudge;
  onLaunchCampaign: (nudgeId: number) => Promise<void>;
  isLoading: boolean;
}

const GrowthOpportunityCard: React.FC<GrowthOpportunityCardProps> = ({ nudge, onLaunchCampaign, isLoading }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  
  const payload = nudge.ai_suggestion_payload || {};
  const opportunityType = payload.opportunity_type || 'GROWTH_OPPORTUNITY';
  const customerIds = payload.customer_ids || [];
  const draftMessage = payload.draft_message || 'No draft message available.';
  const numCustomers = customerIds.length;

  let title = "Growth Opportunity";
  if (opportunityType === 'REFERRAL_CAMPAIGN') title = "Referral Campaign";
  if (opportunityType === 'RE_ENGAGEMENT_CAMPAIGN') title = "Re-engagement Campaign";

  const handleLaunchClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation(); // Prevent card from toggling expansion
    // No confirmation needed for creating drafts.
    onLaunchCampaign(nudge.id);
  };

  return (
    <div className="bg-slate-800/60 border border-slate-700 rounded-xl shadow-lg transition-all duration-300 ease-in-out hover:border-purple-500/50">
      <div 
        className="p-5 cursor-pointer"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            <div className="flex-shrink-0 w-12 h-12 bg-gradient-to-br from-purple-500 to-indigo-600 rounded-lg flex items-center justify-center text-white">
              <TrendingUpIcon className="w-7 h-7" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-slate-50">{title}</h3>
              <p className="text-sm text-slate-400">{nudge.message_snippet}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-slate-400 text-sm font-semibold">
            <UsersIcon className="w-4 h-4" />
            <span>{numCustomers}</span>
          </div>
        </div>
      </div>

      {isExpanded && (
        <div className="border-t border-slate-700/80 bg-slate-900/50 px-5 py-4">
          <p className="text-sm text-slate-300 font-medium mb-3">AI Suggestion:</p>
          <p className="text-sm text-slate-400 mb-4">{nudge.ai_suggestion}</p>
          
          <div className="bg-slate-800/70 p-4 rounded-lg border border-slate-600/50 mb-4">
            <p className="text-xs uppercase font-semibold tracking-wider text-purple-300 mb-2">Draft Message</p>
            <p className="text-slate-300 text-sm italic">"{draftMessage.replace('{customer_name}', '[Customer Name]')}"</p>
            <p className="text-xs text-slate-500 mt-2">Note: [Customer Name] will be personalized for each recipient.</p>
          </div>

          <button
            onClick={handleLaunchClick}
            disabled={isLoading}
            className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-purple-500 to-pink-500 text-white font-bold py-3 px-4 rounded-lg shadow-lg hover:scale-[1.02] transition-transform duration-200 disabled:opacity-50 disabled:cursor-not-allowed disabled:scale-100"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" /> Creating Drafts...
              </>
            ) : (
              <>
                <ArrowRight className="w-5 h-5" /> Review & Edit
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
};

export default GrowthOpportunityCard;