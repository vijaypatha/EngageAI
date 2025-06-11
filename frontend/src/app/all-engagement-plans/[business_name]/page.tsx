'use client';

import { useEffect, useState, useMemo, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { apiClient } from '@/lib/api';
// Updated imports for robust date calculation
import { format, isThisWeek, parseISO, isToday, isTomorrow, addWeeks, startOfWeek, endOfWeek } from 'date-fns';
import { OptInStatusBadge } from '@/components/OptInStatus';
import type { OptInStatus as OptInStatusType } from "@/components/OptInStatus";
import { Loader2, Calendar, ChevronDown } from 'lucide-react';

// @ts-ignore
import { zonedTimeToUtc, utcToZonedTime } from "date-fns-tz";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";


// --- Interfaces ---
interface CustomerMessageFromServer {
  id: number;
  status: string;
  smsContent: string;
  smsTiming: string;
  send_datetime_utc: string;
  source: 'roadmap' | 'scheduled' | 'roadmap_bulk';
  customer_timezone: string | null;
  message_metadata?: {
    roadmap_id?: number;
    [key: string]: any;
  };
}
interface CustomerEngagementFromServer {
  customer_id: number;
  customer_name: string;
  messages: CustomerMessageFromServer[];
  opted_in: boolean;
  latest_consent_status?: string;
  latest_consent_updated?: string;
}
interface EngagementPlan {
  id: number;
  customer_id: number;
  customer_name: string;
  status: string;
  smsContent: string;
  send_datetime_utc: string;
  source: 'roadmap' | 'scheduled' | 'roadmap_bulk';
  latest_consent_status: OptInStatusType;
  latest_consent_updated: string | null;
  customer_timezone: string | null;
  original_roadmap_id?: number;
}

const robustDateSort = (a: EngagementPlan, b: EngagementPlan): number => {
  let timeA = 0;
  let timeB = 0;
  try {
    if (a.send_datetime_utc) {
      const dateA = parseISO(a.send_datetime_utc);
      if (!isNaN(dateA.getTime())) timeA = dateA.getTime();
    }
  } catch (e) { /* Keep timeA as 0 */ }
  try {
    if (b.send_datetime_utc) {
      const dateB = parseISO(b.send_datetime_utc);
      if (!isNaN(dateB.getTime())) timeB = dateB.getTime();
    }
  } catch (e) { /* Keep timeB as 0 */ }
  return timeA - timeB;
};

// The custom isNextWeek function is no longer needed with the new logic.

export default function AllEngagementPlansPage() {
  const params = useParams();
  const business_name = params?.business_name as string | undefined;

  const [plans, setPlans] = useState<EngagementPlan[]>([]);
  const [businessId, setBusinessId] = useState<number | null>(null);
  const [editingPlanId, setEditingPlanId] = useState<number | null>(null);
  const [editingPlanSource, setEditingPlanSource] = useState<'roadmap' | 'scheduled' | 'roadmap_bulk' | null>(null);

  const [editedContent, setEditedContent] = useState<string>("");
  const [editedDate, setEditedDate] = useState<string>("");
  const [editedTime, setEditedTime] = useState<string>("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isBulkSubmitting, setIsBulkSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bulkResult, setBulkResult] = useState<{ scheduled: number; skipped: number } | null>(null);

  const fetchPlans = useCallback(async (showLoadingIndicator = true) => {
    if (!business_name) {
      setError("Business name not found in URL.");
      if(showLoadingIndicator) setIsLoading(false);
      return;
    }
    if(showLoadingIndicator) setIsLoading(true);
    setError(null);
    setBulkResult(null);
    try {
      let currentBusinessId = businessId;
      if (!currentBusinessId) {
        const businessRes = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
        currentBusinessId = businessRes.data.business_id as number;
        setBusinessId(currentBusinessId);
      }

      const response = await apiClient.get<CustomerEngagementFromServer[]>(`/review/all-engagements?business_id=${currentBusinessId}`);

      const processedMessages: EngagementPlan[] = [];
      const scheduledRoadmapIds = new Set<number>();

      if (Array.isArray(response.data)) {
        response.data.forEach(customer => {
          if (Array.isArray(customer.messages)) {
            customer.messages.forEach(message => {
              if (message.source === 'scheduled' && message.message_metadata?.roadmap_id) {
                scheduledRoadmapIds.add(message.message_metadata.roadmap_id);
              }
            });
          }
        });

        response.data.forEach((customer) => {
          if (Array.isArray(customer.messages)) {
            customer.messages.forEach((message) => {
              if (message.status === 'superseded') return;
              if (message.source === 'roadmap' && scheduledRoadmapIds.has(message.id)) return;

              let mappedConsentStatus: OptInStatusType = "waiting";
              const rawConsent = customer.latest_consent_status?.toLowerCase();
              if (customer.opted_in && rawConsent === "opted_in") mappedConsentStatus = "opted_in";
              else if (rawConsent === "opted_out" || rawConsent === "declined") mappedConsentStatus = "opted_out";
              else if (rawConsent === "pending") mappedConsentStatus = "pending";

              processedMessages.push({
                id: Number(message.id),
                customer_id: Number(customer.customer_id),
                customer_name: String(customer.customer_name),
                status: String(message.status),
                smsContent: String(message.smsContent),
                send_datetime_utc: message.send_datetime_utc || new Date(0).toISOString(),
                source: message.source,
                latest_consent_status: mappedConsentStatus,
                latest_consent_updated: customer.latest_consent_updated || null,
                customer_timezone: message.customer_timezone,
                original_roadmap_id: message.message_metadata?.roadmap_id
              });
            });
          }
        });
      }
      processedMessages.sort(robustDateSort);
      setPlans(processedMessages);

    } catch (err: any) {
      console.error('Error fetching plans:', err);
      setError(`Failed to load engagement plans: ${err.response?.data?.detail || err.message}.`);
      setPlans([]);
    } finally {
      if(showLoadingIndicator) setIsLoading(false);
    }
  }, [business_name, businessId]);

  useEffect(() => {
    if (business_name) {
        fetchPlans();
    }
  }, [business_name, fetchPlans]);

  const handleBulkSchedule = async (plansToSchedule: EngagementPlan[], type: string) => {
    setError(null);
    setBulkResult(null);

    const roadmapIds = plansToSchedule
      .filter(p => p.source === 'roadmap' && p.status !== 'superseded' && p.status !== 'scheduled')
      .map(p => p.id);

    if (roadmapIds.length === 0) {
      setError(`No pending roadmap plans found for "${type}".`);
      return;
    }

    setIsBulkSubmitting(true);
    try {
      const response = await apiClient.post('/roadmap-workflow/schedule-bulk', { roadmap_ids: roadmapIds });
      const { scheduled_count, skipped_count } = response.data;
      setBulkResult({ scheduled: scheduled_count, skipped: skipped_count });
      await fetchPlans(false);
    } catch (err: any) {
      console.error("Failed to bulk schedule messages:", err);
      setError(err.response?.data?.detail || 'Failed to schedule messages. Please try again.');
    } finally {
      setIsBulkSubmitting(false);
    }
  };

  const getPendingRoadmapPlans = () => {
    return plans.filter(p => p.source === 'roadmap' && p.status !== 'superseded' && p.status !== 'scheduled');
  };

  const handleDelete = async (planToDelete: EngagementPlan) => {
    setError(null);
    setIsSubmitting(true);
    try {
      const apiSource = planToDelete.source === 'roadmap_bulk' ? 'scheduled' : planToDelete.source;
      await apiClient.delete(`/roadmap-workflow/<span class="math-inline">\{planToDelete\.id\}?source\=</span>{apiSource}`);
      await fetchPlans(false);
    } catch (err: any) {
      if (err.response?.status === 404) {
        console.warn(`Attempted to delete item ID ${planToDelete.id}, but it was not found on the server (already deleted). Refreshing UI.`);
        await fetchPlans(false);
      } else {
        console.error("Failed to delete message:", err);
        const errorDetail = err.response?.data?.detail || 'Failed to delete message. Please try again.';
        setError(errorDetail);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleEdit = (planToEdit: EngagementPlan) => {
    setEditingPlanId(planToEdit.id);
    setEditingPlanSource(planToEdit.source);
    setEditedContent(planToEdit.smsContent);
    setError(null);
    try {
      const utcDate = parseISO(planToEdit.send_datetime_utc || new Date().toISOString());
      if (isNaN(utcDate.getTime())) throw new Error("Invalid date string for editing");
      setEditedDate(format(utcDate, "yyyy-MM-dd"));
      const customerTz = planToEdit.customer_timezone || "America/Denver";
      const localDate = utcToZonedTime(utcDate, customerTz);
      setEditedTime(format(localDate, "HH:mm"));
    } catch (parseError: any) {
      console.error(`Error parsing date for plan ${planToEdit.id}:`, parseError);
      const now = new Date();
      const customerTz = planToEdit.customer_timezone || "America/Denver";
      const localNow = utcToZonedTime(now, customerTz);
      setEditedDate(format(localNow, "yyyy-MM-dd"));
      setEditedTime(format(localNow, "HH:mm"));
      setError(`Could not parse date for message ID ${planToEdit.id}. Please set manually.`);
    }
  };

  const handleCancelEdit = () => {
    setEditingPlanId(null);
    setEditingPlanSource(null);
    setError(null);
  };

  const handleSaveEdit = async () => {
    if (editingPlanId === null || editingPlanSource === null) return;
    setError(null);
    setIsSubmitting(true);
    try {
      const localDateTimeString = `<span class="math-inline">\{editedDate\}T</span>{editedTime}:00`;
      const localDate = new Date(localDateTimeString);
      if (isNaN(localDate.getTime())) {
        setError("Invalid date or time entered.");
        setIsSubmitting(false);
        return;
      }
      const planBeingEdited = plans.find(p => p.id === editingPlanId && p.source === editingPlanSource);
      const customerTz = planBeingEdited?.customer_timezone || "America/Denver";
      const utcDateISOString = zonedTimeToUtc(localDate, customerTz).toISOString();

      await apiClient.put(`/roadmap-workflow/update-time/<span class="math-inline">\{editingPlanId\}?source\=</span>{editingPlanSource}`, {
        smsContent: editedContent,
        send_datetime_utc: utcDateISOString,
      });
      await fetchPlans(false);
      handleCancelEdit();
    } catch (err: any) {
      console.error("Failed to save edited message:", err);
      setError(err.response?.data?.detail || 'Failed to save changes.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSchedule = async (planToSchedule: EngagementPlan) => {
    setError(null);
    setIsSubmitting(true);
    try {
      await apiClient.put(`/roadmap-workflow/${planToSchedule.id}/schedule`);
      await fetchPlans(false);
    } catch (err: any) {
      console.error("Failed to schedule message:", err);
      setError(`Failed to schedule message ID ${planToSchedule.id}: ${err.response?.data?.detail}.`);
    } finally {
      setIsSubmitting(false);
    }
  };
  
  // --- FINAL CORRECTED Grouping Logic ---
  const groupedPlans = useMemo(() => {
    const groups: Record<string, EngagementPlan[]> = {};
    const weekOptions = { weekStartsOn: 1 as const }; // Monday
    const now = new Date();

    // Define the start and end of next week for a reliable comparison
    const startOfNextWeek = startOfWeek(addWeeks(now, 1), weekOptions);
    const endOfNextWeek = endOfWeek(addWeeks(now, 1), weekOptions);

    plans.forEach((plan) => {
      let groupKey = 'Undated';
      try {
        if (plan.send_datetime_utc) {
          const date = parseISO(plan.send_datetime_utc);
          if (!isNaN(date.getTime())) {
            if (isToday(date)) {
              groupKey = 'Today';
            } else if (isTomorrow(date)) {
              groupKey = 'Tomorrow';
            } else if (isThisWeek(date, weekOptions)) {
              groupKey = 'Upcoming';
            } else if (date >= startOfNextWeek && date <= endOfNextWeek) { // This is the robust check
              groupKey = 'Next Week';
            } else {
              groupKey = format(date, 'MMMM yyyy');
            }
          }
        }
      } catch (error) {
        console.error(`Error processing date for plan ID ${plan.id}:`, error);
        groupKey = 'Undated';
      }
      if (!groups[groupKey]) {
        groups[groupKey] = [];
      }
      groups[groupKey].push(plan);
    });
    return groups;
  }, [plans]);

  // --- CORRECTED Group Order Sorting ---
  const groupOrder = useMemo(() => {
    const order = ['Today', 'Tomorrow', 'Upcoming', 'Next Week'];
    const monthKeys = Object.keys(groupedPlans)
      .filter(key => !order.includes(key) && key !== 'Undated')
      .sort((a, b) => {
          // Correctly parse "Month yyyy" strings for chronological sorting
          const dateA = new Date(`1 ${a}`);
          const dateB = new Date(`1 ${b}`);
          return dateA.getTime() - dateB.getTime();
      });
    return [...order, ...monthKeys, 'Undated'];
  }, [groupedPlans]);
  
  const getPendingForGroup = (groupName: string) => {
    return (groupedPlans[groupName] || []).filter(p => p.source === 'roadmap');
  };

  const getPlanKey = (plan: EngagementPlan): string => `<span class="math-inline">\{plan\.source\}\-</span>{plan.id}-${plan.customer_id}`;

  if (isLoading) {
    return (
      <div className="flex-1 p-6 bg-slate-900 text-white min-h-screen flex items-center justify-center">
        <div className="text-center">
            <Loader2 className="animate-spin h-10 w-10 text-purple-400 mx-auto mb-4" />
            <h1 className="text-2xl font-bold text-slate-300">Loading All Nudge Plans...</h1>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 p-6 md:p-8 bg-slate-900 text-slate-100 min-h-screen font-sans">
      <div className="max-w-7xl mx-auto">
        <div className="flex flex-col sm:flex-row justify-between items-start mb-6">
            <div>
                <h1 className="text-4xl font-bold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-pink-500 mb-2">
                    📬 All Nudge Plans
                </h1>
                {business_name && <p className="text-sm text-slate-400">For: {decodeURIComponent(business_name)}</p>}
            </div>
            
            <div className="flex items-center gap-2 mt-4 sm:mt-0">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" className="bg-slate-800 border-slate-700 hover:bg-slate-700 text-white">
                    <Calendar className="mr-2 h-4 w-4" />
                    Bulk Schedule
                    <ChevronDown className="ml-2 h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent className="bg-slate-800 border-slate-700 text-white">
                  <DropdownMenuItem
                    disabled={isBulkSubmitting || getPendingForGroup('Today').length === 0}
                    onSelect={() => handleBulkSchedule(getPendingForGroup('Today'), 'Today')}
                  >
                    Schedule Today ({getPendingForGroup('Today').length})
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    disabled={isBulkSubmitting || getPendingForGroup('Tomorrow').length === 0}
                    onSelect={() => handleBulkSchedule(getPendingForGroup('Tomorrow'), 'Tomorrow')}
                  >
                    Schedule Tomorrow ({getPendingForGroup('Tomorrow').length})
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    disabled={isBulkSubmitting || getPendingForGroup('Upcoming').length === 0}
                    onSelect={() => handleBulkSchedule(getPendingForGroup('Upcoming'), 'Upcoming')}
                  >
                    Schedule Upcoming ({getPendingForGroup('Upcoming').length})
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    disabled={isBulkSubmitting || getPendingForGroup('Next Week').length === 0}
                    onSelect={() => handleBulkSchedule(getPendingForGroup('Next Week'), 'Next Week')}
                  >
                    Schedule Next Week ({getPendingForGroup('Next Week').length})
                  </DropdownMenuItem>
                   <DropdownMenuItem
                    disabled={isBulkSubmitting || getPendingRoadmapPlans().length === 0}
                    onSelect={() => handleBulkSchedule(getPendingRoadmapPlans(), 'All')}
                  >
                    Schedule All Pending ({getPendingRoadmapPlans().length})
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
        </div>

        {isBulkSubmitting && (
          <div className="bg-blue-500/10 border border-blue-500/30 text-blue-300 px-4 py-3 rounded-lg relative mb-6 shadow-lg flex items-center">
            <Loader2 className="mr-3 h-5 w-5 animate-spin"/>
            <p className="font-semibold">Bulk scheduling in progress...</p>
          </div>
        )}
        {bulkResult && (
          <div className="bg-green-500/10 border border-green-500/30 text-green-300 px-4 py-3 rounded-lg relative mb-6 shadow-lg" role="alert">
              <p className="font-bold">Bulk Schedule Complete: {bulkResult.scheduled} succeeded, {bulkResult.skipped} skipped.</p>
              <button onClick={() => setBulkResult(null)} className="absolute top-0 bottom-0 right-0 px-4 py-3 font-bold text-2xl">&times;</button>
          </div>
        )}
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 text-red-300 px-4 py-3 rounded-lg relative mb-6 shadow-lg" role="alert">
            <div className="flex">
                <div className="py-1"><svg className="fill-current h-6 w-6 text-red-400 mr-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><path d="M2.93 17.07A10 10 0 1 1 17.07 2.93 10 10 0 0 1 2.93 17.07zM9 5v6h2V5H9zm0 8v2h2v-2H9z"/></svg></div>
                <div>
                    <p className="font-bold">Error Occurred</p>
                    <p className="text-sm">{error}</p>
                </div>
            </div>
            <button onClick={() => { setError(null); fetchPlans();}} className="absolute top-0 bottom-0 right-0 px-4 py-3 text-red-300 hover:text-red-100 font-bold text-2xl">&times;</button>
          </div>
        )}

        {Object.keys(groupedPlans).length === 0 && !isLoading && !error ? (
             <div className="text-center py-16">
                <svg xmlns="http://www.w3.org/2000/svg" className="mx-auto h-16 w-16 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5.586 15H4a1 1 0 01-1-1V4a1 1 0 011-1h16a1 1 0 011 1v10a1 1 0 01-1 1h-1.586l-2.707 2.707A.996.996 0 0115 17v-2H9v2c0 .399-.216.764-.553.924L5.586 15zM15 9a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
                <p className="mt-5 text-xl text-slate-400 font-semibold">No Engagement Plans Found</p>
                <p className="text-sm text-slate-500 mt-1">There are no messages to schedule or pending review for this business.</p>
            </div>
        ) : (
            groupOrder.map(groupName => (
              (groupedPlans[groupName] && groupedPlans[groupName].length > 0) && (
                <div key={groupName} className="mb-12 last:mb-6">
                    <h2 className="text-2xl font-semibold mb-6 text-slate-300 border-b-2 border-slate-700 pb-3">{groupName}</h2>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {groupedPlans[groupName].map((plan) => {
                        let formattedDate = "N/A", formattedTime = "N/A";
                        const timezoneDisplay = plan.customer_timezone || "America/Denver";
                        if (plan.send_datetime_utc) {
                            try {
                                const localDateInstance = utcToZonedTime(parseISO(plan.send_datetime_utc), timezoneDisplay);
                                formattedDate = format(localDateInstance, 'MMM d, yyyy');
                                formattedTime = format(localDateInstance, 'EEEE, h:mm a');
                            } catch (e) { /* silent fail */ }
                        }
                        const isEditingThisPlan = editingPlanId === plan.id && editingPlanSource === plan.source;
                        return (
                        <div key={getPlanKey(plan)}
                             className={`rounded-xl p-5 transition-all duration-300 shadow-lg hover:shadow-purple-500/20
                                        ${isEditingThisPlan ? 'ring-2 ring-purple-500 shadow-purple-500/30' : ''}
                                        ${plan.status === "scheduled" ? "bg-green-600/10 border border-green-500/30"
                                            : plan.status === "sent" ? "bg-blue-600/10 border border-blue-500/30"
                                            : "bg-slate-800/70 border border-slate-700"}`}>
                            <div className="flex justify-between items-start mb-3">
                                <div>
                                    <p className="text-sm font-semibold text-slate-300">{plan.customer_name}</p>
                                    <p className="text-xs text-slate-400">Cust ID: {plan.customer_id} <OptInStatusBadge status={plan.latest_consent_status} lastUpdated={plan.latest_consent_updated} /></p>
                                </div>
                                <span className={`text-xs font-semibold uppercase px-3 py-1 rounded-full tracking-wider ${
                                    plan.status === "scheduled" ? "bg-green-500/80 text-white"
                                    : plan.status === "sent" ? "bg-blue-500/80 text-white"
                                    : "bg-yellow-500/80 text-slate-900"}`}>
                                    {plan.status.replace('_', ' ')}
                                </span>
                            </div>

                            <div className="mb-3 border-t border-slate-700 pt-3">
                                <p className="text-sm font-medium text-slate-300">{formattedDate} at {formattedTime}</p>
                                <p className="text-xs text-slate-500">({timezoneDisplay.split('/')[1]?.replace('_', ' ') || 'Local'})</p>
                            </div>

                            {isEditingThisPlan ? (
                            <div className="space-y-3 mt-2">
                                <textarea value={editedContent} onChange={(e) => setEditedContent(e.target.value)}
                                    className="w-full p-3 text-sm text-slate-100 bg-slate-700 border border-slate-600 rounded-md focus:ring-2 focus:ring-purple-500"
                                    rows={4} />
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                    <input type="date" value={editedDate} onChange={(e) => setEditedDate(e.target.value)}
                                        className="w-full p-3 text-sm text-slate-100 bg-slate-700 border border-slate-600 rounded-md focus:ring-2 focus:ring-purple-500" />
                                    <input type="time" value={editedTime} onChange={(e) => setEditedTime(e.target.value)}
                                        className="w-full p-3 text-sm text-slate-100 bg-slate-700 border border-slate-600 rounded-md focus:ring-2 focus:ring-purple-500" />
                                </div>
                                <div className="flex justify-end gap-3 pt-2">
                                    <button onClick={handleCancelEdit} className="text-sm px-4 py-2 bg-slate-600 hover:bg-slate-500 rounded-md">Cancel</button>
                                    <button onClick={handleSaveEdit} disabled={isSubmitting} className="text-sm px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-md flex items-center disabled:opacity-70">
                                        {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Save
                                    </button>
                                </div>
                            </div>
                            ) : (
                            <div className="mt-1">
                                <p className="text-slate-300 text-sm leading-relaxed mb-4 whitespace-pre-wrap h-20 overflow-y-auto p-1 bg-slate-800/30 rounded-md scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-slate-800/50">{plan.smsContent}</p>
                                <div className="flex justify-end gap-2 items-center pt-2 border-t border-slate-700/50">
                                <button onClick={() => handleDelete(plan)} disabled={isSubmitting} title="Remove"
                                    className="text-xs p-2 bg-red-700/40 hover:bg-red-600/60 rounded-md text-red-300 hover:text-white disabled:opacity-70">
                                    {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin"/> : <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4"><path fillRule="evenodd" d="M8.75 1A2.75 2.75 0 006 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 10.23 1.482l.149-.022.841 10.518A2.75 2.75 0 007.596 19h4.807a2.75 2.75 0 002.742-2.53l.841-10.52.149.023a.75.75 0 00.23-1.482A41.03 41.03 0 0014 4.193v-.443A2.75 2.75 0 0011.25 1h-2.5zM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4zM8.58 7.72a.75.75 0 00-1.5.06l.3 7.5a.75.75 0 101.5-.06l-.3-7.5zm4.34.06a.75.75 0 10-1.5-.06l-.3 7.5a.75.75 0 101.5.06l.3-7.5z" clipRule="evenodd" /></svg>}
                                </button>
                                <button onClick={() => handleEdit(plan)} disabled={isSubmitting} title="Edit"
                                    className="text-xs p-2 bg-blue-600/40 hover:bg-blue-500/60 rounded-md text-blue-300 hover:text-white disabled:opacity-70">
                                     {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin"/> : <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4"><path d="M5.433 13.917l1.262-3.155A4 4 0 017.58 9.42l6.92-6.918a2.121 2.121 0 013 3l-6.92 6.918c-.383.383-.84.685-1.343.886l-3.154 1.262a.5.5 0 01-.65-.65z" /><path d="M3.5 5.75c0-.69-.56-1.25 1.25-1.25H10A.75.75 0 0010 3H4.75A2.75 2.75 0 002 5.75v9.5A2.75 2.75 0 004.75 18h9.5A2.75 2.75 0 0017 15.25V10a.75.75 0 00-1.5 0v5.25c0 .69-.56 1.25-1.25 1.25h-9.5c-.69 0-1.25-.56-1.25-1.25v-9.5z" /></svg>}
                                </button>
                                {plan.source === 'roadmap' && plan.status !== "scheduled" && plan.status !== "sent" && plan.status !== "superseded" && (
                                <button onClick={() => handleSchedule(plan)} title="Schedule"
                                    disabled={plan.latest_consent_status === "opted_out" || isSubmitting}
                                    className={`text-xs p-2 rounded-md text-white flex items-center space-x-1 disabled:opacity-70
                                                ${plan.latest_consent_status === "opted_out"
                                                    ? 'bg-slate-600 cursor-not-allowed'
                                                    : 'bg-purple-600/70 hover:bg-purple-500/90'}`}>
                                    {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin"/> : <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4"><path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" /></svg>}
                                    <span>Schedule</span>
                                </button>
                                )}
                                </div>
                            </div>
                            )}
                        </div>
                        );
                    })}
                    </div>
                </div>
                )
            ))
        )}
      </div>
    </div>
  );
}