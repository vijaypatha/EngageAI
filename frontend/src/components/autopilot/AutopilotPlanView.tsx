// frontend/src/components/autopilot/AutopilotPlanView.tsx
"use client";

import InstantRepliesManager from './InstantRepliesManager';
import ScheduledMessagesView from './ScheduledMessagesView';

interface AutopilotPlanViewProps {
  businessId: number;
  businessSlug: string; // Pass slug for navigation
}

export default function AutopilotPlanView({ businessId, businessSlug }: AutopilotPlanViewProps) {
    return (
        <div className="flex-1 p-6 md:p-8 bg-slate-900 text-slate-100 min-h-screen font-sans">
            <div className="max-w-7xl mx-auto">
                {/* --- HEADER --- */}
                <div className="flex flex-col sm:flex-row justify-between items-start mb-8">
                    <div>
                        <h1 className="text-4xl font-bold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-pink-500 mb-2">
                            Autopilot Control Center
                        </h1>
                        <p className="text-sm text-slate-400">Manage all scheduled messages and instant auto-replies.</p>
                    </div>
                </div>

                {/* --- Section 1: Instant Auto-Replies Manager --- */}
                <div className="mb-12">
                    <InstantRepliesManager businessId={businessId} businessSlug={businessSlug} />
                </div>

                {/* --- Section 2: Scheduled Messages View --- */}
                <div>
                    <h2 className="text-3xl font-bold text-slate-200 mb-6 border-b border-slate-700 pb-3">
                        Scheduled Flight Plan
                    </h2>
                    <ScheduledMessagesView businessId={businessId} />
                </div>
            </div>
        </div>
    );
}