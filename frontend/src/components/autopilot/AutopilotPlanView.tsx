// frontend/src/components/autopilot/AutopilotPlanView.tsx
"use client";

import { useState, useEffect, useCallback, useMemo } from 'react';
import { apiClient } from '@/lib/api';
import { ApprovalQueueItem } from '@/types';
import InstantRepliesManager from './InstantRepliesManager';
import ScheduledMessagesView from './ScheduledMessagesView';
import ApprovalCard from './ApprovalCard';
import { Inbox, CheckCircle, Loader2, Bot, CalendarDays, Save, ThumbsUp, ThumbsDown, ChevronDown, Info } from 'lucide-react';
import { format } from 'date-fns';
import clsx from 'clsx';

interface AutopilotPlanViewProps {
  businessId: number;
  businessSlug: string;
}

// Type definition for grouped campaigns
type CampaignGroup = {
  campaignType: string;
  items: ApprovalQueueItem[];
  reasonToBelieve?: string; // Add the new field
};

// Sub-component for the Approval Queue section with Accordion UI
function ApprovalQueue({ businessId, onScheduleSuccess }: { businessId: number, onScheduleSuccess: () => void }) {
  const [queue, setQueue] = useState<ApprovalQueueItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [editingItem, setEditingItem] = useState<ApprovalQueueItem | null>(null);
  const [editedContent, setEditedContent] = useState('');
  const [editedDateTime, setEditedDateTime] = useState('');
  const [expandedCampaign, setExpandedCampaign] = useState<string | null>(null);

  const fetchQueue = useCallback(async () => {
    setIsLoading(true); setError(null);
    try {
      const response = await apiClient.get<ApprovalQueueItem[]>(`/approvals/?business_id=${businessId}`);
      setQueue(response.data);
      if (response.data.length > 0) {
        const firstCampaignType = response.data[0].message_metadata?.campaign_type || 'Miscellaneous Suggestions';
        setExpandedCampaign(firstCampaignType);
      }
    } catch (err) {
      setError("Could not load the approval queue.");
    } finally {
      setIsLoading(false);
    }
  }, [businessId]);

  useEffect(() => { if (businessId) { fetchQueue(); } }, [fetchQueue, businessId]);

  const handleOpenScheduleModal = (item: ApprovalQueueItem) => {
    setEditingItem(item);
    setEditedContent(item.content);
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    tomorrow.setHours(10, 0, 0, 0);
    setEditedDateTime(format(tomorrow, "yyyy-MM-dd'T'HH:mm"));
  };

  const handleConfirmSchedule = async () => {
    if (!editingItem) return;
    setIsSubmitting(true);
    try {
      const payload: { content?: string; send_datetime_utc?: string } = {};
      if (editedContent !== editingItem.content) payload.content = editedContent;
      if (editedDateTime) payload.send_datetime_utc = new Date(editedDateTime).toISOString();
      await apiClient.post(`/approvals/${editingItem.id}/approve`, payload);
      setQueue(prev => prev.filter(item => item.id !== editingItem.id));
      setEditingItem(null);
      onScheduleSuccess();
    } catch (error) { console.error("Failed to schedule:", error); }
    finally { setIsSubmitting(false); }
  };
  
  const handleReject = async (id: number) => {
    setQueue(prev => prev.filter(item => item.id !== id));
    try { await apiClient.post(`/approvals/${id}/reject`); }
    catch (error) { fetchQueue(); }
  };

  const handleBulkAction = async (ids: number[], action: 'approve' | 'reject') => {
      setIsSubmitting(true);
      try {
          await apiClient.post('/approvals/bulk-action', { message_ids: ids, action });
          setQueue(prev => prev.filter(item => !ids.includes(item.id)));
          if (action === 'approve') onScheduleSuccess();
      } catch (error) {
          console.error(`Failed to bulk ${action}:`, error);
          fetchQueue();
      } finally {
          setIsSubmitting(false);
      }
  };

  // Grouping Logic for Campaigns, now includes reason_to_believe
  const campaignGroups = useMemo(() => {
    const groups: Record<string, CampaignGroup> = {};
    for (const item of queue) {
      const campaignType = item.message_metadata?.campaign_type || 'Miscellaneous Suggestions';
      if (!groups[campaignType]) {
        groups[campaignType] = {
          campaignType,
          items: [],
          reasonToBelieve: item.message_metadata?.reason_to_believe
        };
      }
      groups[campaignType].items.push(item);
    }
    return Object.values(groups);
  }, [queue]);

  return (
    <>
      <section id="approval-queue">
        <div className="flex items-center gap-4 mb-6">
          <div className="flex-shrink-0 bg-yellow-400/10 text-yellow-300 p-3 rounded-full"><Inbox className="w-6 h-6"/></div>
          <div>
            <h2 className="text-2xl font-bold text-white">Approval Queue</h2>
            <p className="text-sm text-slate-400">Review and schedule AI-drafted messages.</p>
          </div>
        </div>

        {isLoading ? (
          <div className="flex justify-center p-10"><Loader2 className="w-8 h-8 animate-spin text-purple-400" /></div>
        ) : error ? (
          <div className="p-4 bg-red-900/20 text-red-400 rounded-lg">{error}</div>
        ) : queue.length === 0 ? (
          <div className="text-center py-12 px-6 bg-slate-800/50 rounded-lg border border-slate-700">
            <CheckCircle className="w-14 h-14 text-green-500 mx-auto mb-4" />
            <p className="font-semibold text-white text-lg">Queue is Clear!</p>
            <p className="text-slate-400 text-sm">New AI suggestions will appear here for your review.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {campaignGroups.map(({ campaignType, items, reasonToBelieve }) => {
              const isExpanded = expandedCampaign === campaignType;
              return (
                <div key={campaignType} className="bg-slate-800/50 border border-slate-700 rounded-lg overflow-hidden transition-all duration-300">
                  <div 
                    className="flex items-center justify-between p-4 cursor-pointer hover:bg-slate-800"
                    onClick={() => setExpandedCampaign(isExpanded ? null : campaignType)}
                  >
                    <div className="flex flex-col">
                        <div className="flex items-center gap-3">
                            <h3 className="font-bold text-slate-100 capitalize">{campaignType.replace(/_/g, ' ')}</h3>
                            <span className="text-xs font-semibold bg-slate-700 text-slate-300 px-2 py-0.5 rounded-full">{items.length}</span>
                        </div>
                        {/* --- Reason to Believe Display --- */}
                        {reasonToBelieve && (
                            <p className="mt-1 flex items-center gap-2 text-xs text-slate-400">
                                <Info className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" />
                                <span>{reasonToBelieve}</span>
                            </p>
                        )}
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0 ml-4">
                        <button onClick={(e) => { e.stopPropagation(); handleBulkAction(items.map(i => i.id), 'reject'); }} disabled={isSubmitting} className="px-2.5 py-1.5 text-xs font-semibold text-slate-300 bg-slate-700 hover:bg-red-500/20 hover:text-red-300 rounded-md flex items-center gap-1.5 transition-colors"><ThumbsDown className="w-3.5 h-3.5" /> Reject All</button>
                        <button onClick={(e) => { e.stopPropagation(); handleBulkAction(items.map(i => i.id), 'approve'); }} disabled={isSubmitting} className="px-2.5 py-1.5 text-xs font-semibold text-white bg-green-600/80 hover:bg-green-600 rounded-md flex items-center gap-1.5 transition-colors"><ThumbsUp className="w-3.5 h-3.5" /> Schedule All</button>
                        <ChevronDown className={clsx("w-5 h-5 text-slate-400 transition-transform", { "rotate-180": isExpanded })} />
                    </div>
                  </div>
                  {isExpanded && (
                    <div className="p-4 border-t border-slate-700">
                      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                        {items.map(item => (
                          <ApprovalCard key={item.id} item={item} onSchedule={handleOpenScheduleModal} onReject={handleReject} isProcessing={isSubmitting} />
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {editingItem && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-in fade-in-0">
          <div className="bg-slate-800 border border-slate-700 rounded-lg shadow-xl w-full max-w-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Edit & Schedule Message</h3>
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium text-slate-400 block mb-1">Message Content</label>
                <textarea value={editedContent} onChange={(e) => setEditedContent(e.target.value)} className="w-full h-32 bg-slate-900 p-2 rounded-md text-slate-300 resize-none focus:outline-none focus:ring-2 focus:ring-purple-500" />
              </div>
              <div>
                <label className="text-sm font-medium text-slate-400 block mb-1">Schedule for</label>
                <input type="datetime-local" value={editedDateTime} onChange={(e) => setEditedDateTime(e.target.value)} className="w-full bg-slate-900 p-2 rounded-md text-slate-300 focus:outline-none focus:ring-2 focus:ring-purple-500" />
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => setEditingItem(null)} disabled={isSubmitting} className="px-4 py-2 text-sm font-semibold text-slate-300 bg-slate-700 hover:bg-slate-600 rounded-md">Cancel</button>
              <button onClick={handleConfirmSchedule} disabled={isSubmitting} className="px-4 py-2 text-sm font-semibold text-white bg-purple-600 hover:bg-purple-700 rounded-md flex items-center gap-2">
                {isSubmitting ? <Loader2 className="w-5 h-5 animate-spin"/> : <Save className="w-5 h-5" />}
                {isSubmitting ? 'Scheduling...' : 'Confirm Schedule'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// --- Main Autopilot Page View ---
export default function AutopilotPlanView({ businessId, businessSlug }: AutopilotPlanViewProps) {
    const [refreshKey, setRefreshKey] = useState(0);
    const triggerFlightPlanRefresh = () => setRefreshKey(prev => prev + 1);

    return (
        <div className="flex-1 p-6 md:p-8 bg-slate-900 text-slate-100 min-h-screen font-sans">
            <div className="max-w-7xl mx-auto">
                <div className="mb-12">
                    <h1 className="text-4xl md:text-5xl font-bold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-pink-500">
                        Autopilot Control Center
                    </h1>
                    <p className="mt-2 text-lg text-slate-400">Your central hub for automated customer engagement.</p>
                </div>
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 lg:gap-12 items-start">
                    <div className="lg:col-span-2 space-y-16">
                        <ApprovalQueue businessId={businessId} onScheduleSuccess={triggerFlightPlanRefresh} />
                        <section id="flight-plan">
                             <div className="flex items-center gap-4 mb-6">
                                <div className="flex-shrink-0 bg-green-400/10 text-green-300 p-3 rounded-full"><CalendarDays className="w-6 h-6"/></div>
                                <div>
                                    <h2 className="text-2xl font-bold text-white">Scheduled Flight Plan</h2>
                                    <p className="text-sm text-slate-400">View and manage all upcoming scheduled messages.</p>
                                </div>
                            </div>
                            <ScheduledMessagesView key={refreshKey} businessId={businessId} />
                        </section>
                    </div>
                    <div className="lg:col-span-1 lg:sticky lg:top-8 space-y-12">
                        <section id="instant-replies">
                            <div className="flex items-center gap-4 mb-6">
                                <div className="flex-shrink-0 bg-blue-400/10 text-blue-300 p-3 rounded-full"><Bot className="w-6 h-6"/></div>
                                <div>
                                    <h2 className="text-2xl font-bold text-white">Instant Auto-Replies</h2>
                                    <p className="text-sm text-slate-400">Configure automatic answers.</p>
                                </div>
                            </div>
                            <InstantRepliesManager businessId={businessId} businessSlug={businessSlug} />
                        </section>
                    </div>
                </div>
            </div>
        </div>
    );
}
