'use client';

import { useEffect, useState, useMemo } from 'react';
import { useParams } from 'next/navigation';
import { apiClient } from '@/lib/api';
import { format, isThisWeek, addWeeks, isBefore, parseISO } from 'date-fns';
import { OptInStatusBadge } from '@/components/OptInStatus';
import type { OptInStatus } from "@/components/OptInStatus";
// @ts-ignore
import { zonedTimeToUtc, utcToZonedTime } from "date-fns-tz";

interface CustomerMessage {
  id: number;
  status: string;
  smsContent: string;
  smsTiming: string;
  send_datetime_utc: string;
  source: string;
  customer_timezone: string | null;
}

interface CustomerEngagement {
  customer_id: number;
  customer_name: string;
  messages: CustomerMessage[];
  opted_in: boolean;
  latest_consent_status?: string;
  latest_consent_updated?: string;
}

interface Message {
  message_id: number;
  content: string;
  scheduled_time: string;
  status: string;
}

interface Customer {
  customer_id: number;
  customer_name: string;
  opted_in: boolean;
  latest_consent_status: OptInStatus;
  latest_consent_updated: string | null;
  messages: CustomerMessage[];
}

interface EngagementPlan {
  id: number;
  customer_name: string;
  status: string;
  smsContent: string;
  smsTiming: string;
  send_datetime_utc: string;
  source: string;
  latest_consent_status: OptInStatus;
  latest_consent_updated: string | null;
  customer_timezone: string | null;
  messages: CustomerMessage[];
}

export default function AllEngagementPlansPage() {
  const { business_name } = useParams();
  const [plans, setPlans] = useState<EngagementPlan[]>([]);
  const [businessId, setBusinessId] = useState<number | null>(null);
  const [editingPlan, setEditingPlan] = useState<number | null>(null);
  const [editedContent, setEditedContent] = useState<string>("");
  const [editedTime, setEditedTime] = useState<string>("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchPlans = async () => {
    try {
      setIsLoading(true);
      setError(null);
      
      // First get the business ID
      const businessRes = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
      const businessId = businessRes.data.business_id;
      setBusinessId(businessId);

      // Then fetch all engagements
      const response = await apiClient.get<CustomerEngagement[]>(`/review/all-engagements?business_id=${businessId}`);
      
      // Process the response to flatten customer messages into plans
      const allPlans: EngagementPlan[] = [];
      if (Array.isArray(response.data)) {
        response.data.forEach((customer: CustomerEngagement) => {
          if (Array.isArray(customer.messages)) {
            customer.messages.forEach((message: CustomerMessage) => {
              const { customer_timezone, ...restMessage } = message;
              // Map the status string to OptInStatus
              let mappedStatus: OptInStatus = "waiting";
              if (customer.latest_consent_status === "opted_in" && customer.opted_in) {
                mappedStatus = "opted_in";
              } else if (customer.latest_consent_status === "opted_out" && !customer.opted_in) {
                mappedStatus = "opted_out";
              } else if (customer.latest_consent_status === "pending") {
                mappedStatus = "pending";
              } else if (!customer.latest_consent_status) {
                mappedStatus = "waiting";
              } else {
                mappedStatus = "error";
              }

              allPlans.push({
                ...restMessage,
                customer_name: customer.customer_name,
                latest_consent_status: mappedStatus,
                latest_consent_updated: customer.latest_consent_updated || null,
                customer_timezone: customer_timezone ?? null,
                messages: customer.messages,
              });
            });
          }
        });
      }
      
      setPlans(allPlans);
    } catch (error) {
      console.error('Error fetching plans:', error);
      setError('Failed to load engagement plans. Please try again.');
      setPlans([]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (business_name) {
      fetchPlans();
    }
  }, [business_name]);

  const handleDelete = async (plan: EngagementPlan) => {
    try {
      await apiClient.delete(`/review/${plan.id}?source=${plan.source}`);
      setPlans(prev => prev.filter(p => p.id !== plan.id));
    } catch (err) {
      console.error("❌ Failed to delete message:", err);
      setError('Failed to delete message. Please try again.');
    }
  };

  const handleEdit = (plan: EngagementPlan) => {
    setEditingPlan(plan.id);
    setEditedContent(plan.smsContent);
    setEditedTime(plan.send_datetime_utc);
  };

  const handleSaveEdit = async (plan: EngagementPlan) => {
    try {
      const localDate = new Date(editedTime);
      const utcDate = zonedTimeToUtc(localDate, "America/Denver").toISOString();

      await apiClient.put(`/review/update-time/${plan.id}?source=${plan.source}`, {
        smsContent: editedContent,
        send_datetime_utc: utcDate,
      });

      setPlans(prev =>
        prev.map(p =>
          p.id === plan.id
            ? { ...p, smsContent: editedContent, send_datetime_utc: utcDate }
            : p
        )
      );
      setEditingPlan(null);
    } catch (err) {
      console.error("❌ Failed to save edited message:", err);
      setError('Failed to save changes. Please try again.');
    }
  };

  const handleSchedule = async (plan: EngagementPlan) => {
    try {
      const res = await apiClient.put(`/review/${plan.id}/schedule`);
      const newId = res.data.scheduled_sms_id;

      setPlans(prev =>
        prev.map(p =>
          p.id === plan.id
            ? { ...p, id: newId, status: "scheduled", source: "scheduled" }
            : p
        )
      );
    } catch (err) {
      console.error("❌ Failed to schedule message:", err);
      setError('Failed to schedule message. Please try again.');
    }
  };

  // Group messages by timing with safe checks
  const groupedPlans = useMemo(() => {
    // Ensure we have an array to work with
    if (!Array.isArray(plans)) return {} as Record<string, EngagementPlan[]>;
    
    return plans.reduce((acc, plan) => {
      if (!plan?.send_datetime_utc) return acc;
      
      const date = parseISO(plan.send_datetime_utc);
      const nextWeekStart = addWeeks(new Date(), 1);
      let group = 'Later';
      
      if (isThisWeek(date)) {
        group = 'This Week';
      } else if (isBefore(date, nextWeekStart)) {
        group = 'Next Week';
      }

      if (!acc[group]) {
        acc[group] = [];
      }
      acc[group].push(plan);
      return acc;
    }, {} as Record<string, EngagementPlan[]>);
  }, [plans]);

  if (isLoading) {
    return (
      <div className="flex-1 p-6">
        <div className="max-w-6xl mx-auto">
          <h1 className="text-4xl font-bold mb-2">📬 Loading Engagement Plans...</h1>
          <div className="animate-pulse space-y-4">
            <div className="h-8 bg-gray-700 rounded w-1/4"></div>
            <div className="h-32 bg-gray-700 rounded"></div>
            <div className="h-32 bg-gray-700 rounded"></div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 p-6">
        <div className="max-w-6xl mx-auto">
          <h1 className="text-4xl font-bold mb-2">📬 Engagement Plans</h1>
          <div className="bg-red-500/10 border border-red-500/20 text-red-400 rounded-lg px-4 py-3 mb-4">
            <p>{error}</p>
            <button 
              onClick={fetchPlans}
              className="mt-2 px-4 py-2 bg-red-500/20 hover:bg-red-500/30 rounded-lg transition-colors"
            >
              Try Again
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 p-6">
      <div className="max-w-6xl mx-auto">
        <h1 className="text-4xl font-bold mb-2">📬 Engagement Plans</h1>
        <p className="text-gray-400 mb-8">Grouped SMS plans across all customers</p>

        {['This Week', 'Next Week', 'Later'].map(group => (
          <div key={group} className="mb-12 last:mb-6">
            <h2 className="text-2xl font-semibold mb-6">{group}</h2>
            <div className="space-y-4">
              {groupedPlans[group]?.map(plan => {
                const utcDate = parseISO(plan.send_datetime_utc);
                const localDate = utcToZonedTime(utcDate, plan.customer_timezone || "America/Denver");
                
                return (
                  <div key={plan.id} className="relative">
                    {/* Timeline line */}
                    <div className="absolute left-6 w-1 h-full bg-green-500 rounded-full"></div>
                    
                    {/* Date circle */}
                    <div className="absolute left-6 -translate-x-1/2 w-14 h-14 rounded-full bg-[#2C2F3E] border-2 border-green-500 flex items-center justify-center text-sm shadow-lg shadow-green-500/20">
                      <div className="text-green-400">{format(localDate, 'MMM d')}</div>
                    </div>

                    {/* Content card */}
                    <div className={`ml-20 rounded-lg p-6 relative ${
                      plan.status === "scheduled" 
                        ? "bg-green-900/50 border-2 border-green-600" 
                        : "bg-[#1C1F2E]"
                    }`}>
                      <div className="flex justify-between items-start mb-6">
                        <div className="flex-1 pr-24">
                          <div className="text-lg mb-2">
                            {format(localDate, 'EEEE, h:mm a')} 
                            <span className="text-sm text-gray-400 ml-2">
                              ({(plan.customer_timezone || "America/Denver").split('/')[1].replace('_', ' ')})
                            </span>
                          </div>
                          {editingPlan === plan.id ? (
                            <>
                              <textarea
                                value={editedContent}
                                onChange={(e) => setEditedContent(e.target.value)}
                                className="w-full p-2 text-sm text-white bg-zinc-800 border border-neutral rounded mb-2"
                                rows={3}
                              />
                              <input
                                type="datetime-local"
                                value={editedTime}
                                onChange={(e) => setEditedTime(e.target.value)}
                                className="w-full p-2 text-sm text-white bg-zinc-800 border border-neutral rounded mb-4"
                              />
                            </>
                          ) : (
                            <div className="text-gray-300 mb-4">{plan.smsContent}</div>
                          )}
                          <div className="flex items-center gap-3">
                            <span className="text-gray-400">👤</span>
                            <span className="mr-2">{plan.customer_name}</span>
                            <OptInStatusBadge 
                              status={plan.latest_consent_status}
                              lastUpdated={plan.latest_consent_updated}
                            />
                          </div>
                        </div>
                        
                        {/* Status badge */}
                        <div className={`absolute top-6 right-6 px-3 py-1 rounded-full text-sm font-medium ${
                          plan.status === "scheduled"
                            ? "bg-green-500/20 text-green-300"
                            : plan.status === "sent"
                            ? "bg-blue-500/20 text-blue-300"
                            : plan.status === "rejected"
                            ? "bg-red-500/20 text-red-300"
                            : "bg-yellow-500/20 text-yellow-300"
                        }`}>
                          {plan.status.toUpperCase()}
                        </div>
                      </div>

                      {/* Action buttons */}
                      <div className="flex justify-end gap-2 mt-4">
                        {editingPlan === plan.id ? (
                          <>
                            <button
                              onClick={() => setEditingPlan(null)}
                              className="px-4 py-2 bg-gray-500 hover:bg-gray-600 rounded-lg transition-colors"
                            >
                              Cancel
                            </button>
                            <button
                              onClick={() => handleSaveEdit(plan)}
                              className="px-4 py-2 bg-blue-500 hover:bg-blue-600 rounded-lg transition-colors"
                            >
                              Save
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              onClick={() => handleDelete(plan)}
                              className="px-4 py-2 bg-red-500 hover:bg-red-600 rounded-lg transition-colors"
                            >
                              Remove
                            </button>
                            <button
                              onClick={() => handleEdit(plan)}
                              className="px-4 py-2 bg-blue-500 hover:bg-blue-600 rounded-lg transition-colors"
                            >
                              Edit
                            </button>
                            {plan.status !== "scheduled" && (
                              <button
                                onClick={() => handleSchedule(plan)}
                                className="px-4 py-2 bg-green-500 hover:bg-green-600 rounded-lg transition-colors"
                              >
                                Schedule
                              </button>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
              {groupedPlans[group]?.length === 0 && (
                <div className="text-gray-500 text-center py-8">
                  No messages scheduled for {group.toLowerCase()}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
