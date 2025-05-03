// frontend/src/app/all-engagement-plans/[business_name]/page.tsx

'use client';

import { useEffect, useState, useMemo, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { apiClient } from '@/lib/api';
import { format, isThisWeek, addWeeks, isBefore, parseISO } from 'date-fns';
import { OptInStatusBadge } from '@/components/OptInStatus';
import type { OptInStatus } from "@/components/OptInStatus";
// Using @ts-ignore as proper types might not be installed or included
// @ts-ignore
import { zonedTimeToUtc, utcToZonedTime } from "date-fns-tz"; // For timezone conversions

// Interface for a single message within a customer's engagement data
interface CustomerMessage {
  id: number; // This is the message ID (roadmap or scheduled)
  status: string; // e.g., 'pending_review', 'scheduled', 'sent'
  smsContent: string;
  smsTiming: string; // Original timing string (e.g., "Day 5, 10:00 AM") - might not be directly used here
  send_datetime_utc: string; // ISO string for the scheduled time
  source: string; // e.g., 'roadmap', 'scheduled', 'instant_nudge'
  customer_timezone: string | null; // Customer's specific timezone identifier
}

// Interface for the data structure returned by /review/all-engagements
interface CustomerEngagement {
  customer_id: number;
  customer_name: string;
  messages: CustomerMessage[]; // Array of messages for this customer
  opted_in: boolean;
  latest_consent_status?: string; // Raw status from backend
  latest_consent_updated?: string; // ISO string or null
}

// Interface for the flattened plan object used in the component's state and rendering
// Each object represents one message to be displayed in the timeline
interface EngagementPlan {
  id: number; // The message ID
  customer_id: number; // ID of the customer this message belongs to
  customer_name: string;
  status: string; // Message status
  smsContent: string;
  send_datetime_utc: string; // ISO string
  source: string; // Message source ('roadmap' or 'scheduled')
  latest_consent_status: OptInStatus; // Mapped status for the badge
  latest_consent_updated: string | null; // ISO string or null
  customer_timezone: string | null; // Customer's timezone identifier
}

export default function AllEngagementPlansPage() {
  const params = useParams();
  // Ensure business_name is treated as a string
  const business_name = params?.business_name as string | undefined;

  const [plans, setPlans] = useState<EngagementPlan[]>([]);
  const [businessId, setBusinessId] = useState<number | null>(null);
  const [editingPlan, setEditingPlan] = useState<number | null>(null); // Store the ID of the plan being edited
  const [editedContent, setEditedContent] = useState<string>("");
  const [editedDate, setEditedDate] = useState<string>(""); // Format: minGoto-MM-DD
  const [editedTime, setEditedTime] = useState<string>(""); // Format: HH:mm
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchPlans = useCallback(async () => {
    if (!business_name) {
        setError("Business name not found in URL.");
        setIsLoading(false);
        return;
    }

    try {
      setIsLoading(true);
      setError(null);
      console.log(`Workspaceing plans for business slug: ${business_name}`);

      // 1. Get the business ID from the slug
      const businessRes = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
      const currentBusinessId = businessRes.data.business_id;
      setBusinessId(currentBusinessId);
      console.log(`Business ID found: ${currentBusinessId}`);

      // 2. Fetch all engagement data using the business ID
      const response = await apiClient.get<CustomerEngagement[]>(`/review/all-engagements?business_id=${currentBusinessId}`);
      console.log(`Workspaceed raw engagement data:`, response.data);

      // 3. Process the response: Flatten customer messages into individual plans
      const allPlans: EngagementPlan[] = [];
      if (Array.isArray(response.data)) {
        response.data.forEach((customer: CustomerEngagement) => {
          // Ensure customer.messages is an array before iterating
          if (Array.isArray(customer.messages)) {
            customer.messages.forEach((message: CustomerMessage) => {
              // Extract customer_timezone safely, default to null if missing
              const customer_timezone = message.customer_timezone ?? null;
              const { customer_timezone: _, ...restMessage } = message; // Exclude customer_timezone from restMessage

              // Map the raw consent status string to our OptInStatus enum/type
              let mappedStatus: OptInStatus = "waiting"; // Default status
              const rawStatus = customer.latest_consent_status?.toLowerCase();
              const isOptedIn = customer.opted_in;

              if (rawStatus === "opted_in" && isOptedIn) {
                mappedStatus = "opted_in";
              } else if (rawStatus === "opted_out" || (rawStatus === "declined" && !isOptedIn)) {
                // Consider 'declined' as 'opted_out' for the badge
                mappedStatus = "opted_out";
              } else if (rawStatus === "pending") {
                mappedStatus = "pending";
              } else if (!rawStatus) {
                // If no status exists, treat as 'waiting' (or maybe 'pending' depending on logic)
                mappedStatus = "waiting";
              } else {
                // Handle unexpected statuses, map to 'error' or log a warning
                console.warn(`Unexpected consent status '${rawStatus}' for customer ${customer.customer_id}`);
                mappedStatus = "error";
              }

              // Push a new EngagementPlan object for each message
              allPlans.push({
                ...restMessage, // Spread message details (id, status, smsContent, etc.)
                customer_id: customer.customer_id, // Add customer ID
                customer_name: customer.customer_name,
                latest_consent_status: mappedStatus,
                latest_consent_updated: customer.latest_consent_updated || null, // Use null if undefined
                customer_timezone: customer_timezone, // Add customer timezone
              });
            });
          } else {
            console.warn(`Customer ${customer.customer_id} has no 'messages' array or it's not an array.`);
          }
        });
      } else {
         console.warn(`API response data for /review/all-engagements is not an array:`, response.data);
      }

      console.log(`Processed ${allPlans.length} total plan items.`);
      setPlans(allPlans); // Update state with the flattened list

    } catch (error: any) {
      console.error('Error fetching plans:', error);
      // Provide more specific error message if possible
      const errorDetail = error.response?.data?.detail || error.message || 'Unknown error';
      setError(`Failed to load engagement plans: ${errorDetail}. Please try again.`);
      setPlans([]); // Clear plans on error
    } finally {
      setIsLoading(false);
    }
  }, [business_name]); // Add business_name as dependency

  useEffect(() => {
    fetchPlans();
  }, [fetchPlans]); // Call fetchPlans when the component mounts or fetchPlans changes

  const handleDelete = async (plan: EngagementPlan) => {
    // Optimistic UI update: Remove immediately
    setPlans(prev => prev.filter(p => !(p.id === plan.id && p.source === plan.source)));
    try {
      console.log(`Deleting plan ID: ${plan.id}, Source: ${plan.source}`);
      await apiClient.delete(`/roadmap-workflow/${plan.id}?source=${plan.source}`);
      console.log(`Successfully deleted plan ID: ${plan.id}`);
    } catch (err) {
      console.error("❌ Failed to delete message:", err);
      setError('Failed to delete message. Please try again.');
      // Rollback UI update on failure
      fetchPlans(); // Refetch to get the correct state
    }
  };

  const handleEdit = (plan: EngagementPlan) => {
    console.log(`Editing plan ID: ${plan.id}, Source: ${plan.source}`);
    setEditingPlan(plan.id); // Store the ID of the plan being edited
    setEditedContent(plan.smsContent);

    try {
        // Use current time if send_datetime_utc is invalid or null
        const dateString = plan.send_datetime_utc || new Date().toISOString();
        const utcDate = parseISO(dateString); // Use parseISO for reliability

        // Pre-fill date input (YYYY-MM-DD)
        setEditedDate(format(utcDate, "yyyy-MM-dd"));

        // Convert UTC to customer's local timezone for time input
        // Use a fallback timezone if customer_timezone is null/invalid
        const customerTz = plan.customer_timezone || "America/Denver"; // Fallback timezone
        const localDate = utcToZonedTime(utcDate, customerTz);
        setEditedTime(format(localDate, "HH:mm")); // Format as HH:mm (local time)
    } catch (parseError) {
        console.error(`Error parsing date for plan ${plan.id}:`, parseError);
        // Set defaults if parsing fails
        const now = new Date();
        setEditedDate(format(now, "yyyy-MM-dd"));
        setEditedTime(format(now, "HH:mm"));
        setError(`Could not parse date for message ID ${plan.id}. Please set manually.`);
    }
  };

  const handleSaveEdit = async (plan: EngagementPlan) => {
    try {
      // Combine date and time strings into a local date object
      const localDateTimeString = `${editedDate}T${editedTime}:00`; // Assume seconds are 00
      const localDate = new Date(localDateTimeString); // This creates a Date object in the browser's local time

      // Convert this local date/time to UTC using the customer's timezone
      const customerTz = plan.customer_timezone || "America/Denver"; // Use fallback
      const utcDate = zonedTimeToUtc(localDate, customerTz).toISOString(); // Convert to UTC ISO string
      console.log(`Saving edit for plan ID: ${plan.id}. New UTC time: ${utcDate}`);

      await apiClient.put(`/roadmap-workflow/update-time/${plan.id}?source=${plan.source}`, {
        smsContent: editedContent,
        send_datetime_utc: utcDate, // Send the correctly converted UTC ISO string
      });

      // Update local state optimistically
      setPlans(prev =>
        prev.map(p =>
          (p.id === plan.id && p.source === plan.source) // Ensure we match the correct plan
            ? { ...p, smsContent: editedContent, send_datetime_utc: utcDate }
            : p
        )
      );
      setEditingPlan(null); // Exit editing mode
      console.log(`Successfully saved edit for plan ID: ${plan.id}`);
    } catch (err) {
      console.error("❌ Failed to save edited message:", err);
      setError('Failed to save changes. Please try again.');
    }
  };

  const handleSchedule = async (plan: EngagementPlan) => {
    // Find the original plan in state to potentially update
    const originalPlanIndex = plans.findIndex(p => p.id === plan.id && p.source === plan.source);

    try {
      console.log(`Attempting to schedule plan ID: ${plan.id}, Source: ${plan.source}`);
      const res = await apiClient.put(`/roadmap-workflow/${plan.id}/schedule`);
      console.log(`Schedule API response for ID ${plan.id}:`, res.data);

      // --- FIX: Use message_id from response ---
      const newMessageId = res.data.message_id; // Get the ID of the *new* Message record created
      if (!newMessageId) {
          throw new Error("API response did not include a message_id.");
      }

      // Update the state: Change the status and source, and potentially the ID
       setPlans(prev => {
           const newPlans = [...prev];
           if (originalPlanIndex > -1) {
               // Update the existing plan item in place
               newPlans[originalPlanIndex] = {
                   ...newPlans[originalPlanIndex],
                   id: newMessageId, // Update ID to the new Message record ID
                   status: "scheduled",
                   source: "scheduled" // Update source to 'scheduled'
               };
           } else {
               console.warn(`Plan with ID ${plan.id} and Source ${plan.source} not found in state during schedule update.`);
           }
           return newPlans;
       });

       console.log(`Successfully scheduled message. Original roadmap ID: ${plan.id}, New Message ID: ${newMessageId}`);

    } catch (err: any) {
      console.error("❌ Failed to schedule message:", err);
       const errorDetail = err.response?.data?.detail || err.message || 'Unknown error';
      setError(`Failed to schedule message ID ${plan.id}: ${errorDetail}. Please try again.`);
    }
  };

  // Memoized calculation for grouping plans by time categories
  const groupedPlans = useMemo(() => {
    console.log("Recalculating grouped plans...");
    // Ensure plans is an array before reducing
    if (!Array.isArray(plans)) {
        console.warn("Plans state is not an array, returning empty groups.");
        return {} as Record<string, EngagementPlan[]>;
    }

    const groups: Record<string, EngagementPlan[]> = {
      'This Week': [],
      'Next Week': [],
      'Later': []
    };

    const now = new Date(); // Reference point for 'This Week'/'Next Week'

    return plans.reduce((acc, plan) => {
      // Basic validation for plan structure and date
      if (!plan || typeof plan !== 'object' || !plan.send_datetime_utc || typeof plan.send_datetime_utc !== 'string') {
          console.warn('Skipping invalid plan object:', plan);
          return acc;
      }

      try {
        const date = parseISO(plan.send_datetime_utc); // Use parseISO for reliability
        const nextWeekStart = addWeeks(now, 1);

        let group = 'Later'; // Default group

        // Check if the date is valid before comparing
        if (!isNaN(date.getTime())) {
            if (isThisWeek(date, { weekStartsOn: 1 })) { // weekStartsOn: 1 for Monday
              group = 'This Week';
            } else if (isBefore(date, nextWeekStart)) {
              group = 'Next Week';
            }
        } else {
             console.warn(`Invalid date parsed for plan ID ${plan.id}: ${plan.send_datetime_utc}`);
             group = 'Later';
        }

        acc[group].push(plan);
        return acc;

      } catch (error) {
         console.error(`Error processing date for plan ID ${plan.id}:`, error);
         acc['Later'].push(plan);
         return acc;
      }
    }, groups); // Start with the pre-defined groups object
  }, [plans]); // Dependency array includes 'plans' state

  // Render Loading State
  if (isLoading) {
    return (
      <div className="flex-1 p-6 bg-[#11131E] text-white min-h-screen">
        <div className="max-w-6xl mx-auto">
          <h1 className="text-4xl font-bold mb-2 text-gray-100">📬 Loading Engagement Plans...</h1>
          <div className="animate-pulse space-y-6 mt-8">
            <div className="h-8 bg-gray-700 rounded w-1/3"></div>
            <div className="h-40 bg-gray-700 rounded-lg"></div>
            <div className="h-40 bg-gray-700 rounded-lg"></div>
          </div>
        </div>
      </div>
    );
  }

  // Render Error State
  if (error) {
    return (
      <div className="flex-1 p-6 bg-[#11131E] text-white min-h-screen">
        <div className="max-w-6xl mx-auto">
          <h1 className="text-4xl font-bold mb-2 text-gray-100">📬 Engagement Plans</h1>
          <div className="bg-red-900/30 border border-red-700 text-red-300 rounded-lg px-4 py-3 my-6" role="alert">
            <p className="font-semibold">Error:</p>
            <p>{error}</p>
            <button
              onClick={fetchPlans}
              className="mt-3 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors text-sm font-medium"
            >
              Try Again
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Render Content
  return (
    <div className="flex-1 p-6 bg-[#11131E] text-white min-h-screen">
      <div className="max-w-6xl mx-auto">
        <h1 className="text-4xl font-bold mb-2 text-gray-100">📬 Engagement Plans</h1>
        <p className="text-gray-400 mb-10">View and manage upcoming scheduled messages across all customers.</p>

        {/* Iterate over the defined groups to ensure order */}
        {['This Week', 'Next Week', 'Later'].map(group => (
          <div key={group} className="mb-12 last:mb-6">
            <h2 className="text-2xl font-semibold mb-6 text-gray-200 border-b border-gray-700 pb-2">{group}</h2>
            <div className="space-y-6"> {/* Increased spacing between cards */}
              {groupedPlans[group] && groupedPlans[group].length > 0 ? (
                groupedPlans[group].map((plan, index) => { // Added index for potential logging
                  // --- Date/Time Formatting ---
                  let formattedDate = "---";
                  let formattedTime = "---";
                  const timezoneDisplay = plan.customer_timezone || "America/Denver"; // Fallback

                  try {
                      const utcDate = parseISO(plan.send_datetime_utc);

                      // 1. Check if the initial UTC date parsing is valid
                      if (isNaN(utcDate.getTime())) {
                          throw new Error("Invalid date string received from backend");
                      }

                      // 2. Convert to the target timezone
                      const localDateInstance = utcToZonedTime(utcDate, timezoneDisplay);

                      // 3. Check if the result of timezone conversion is valid (optional but safe)
                      if (isNaN(localDateInstance.getTime())) {
                          throw new Error("Failed to convert date to local timezone");
                      }

                      // 4. Format the valid localDateInstance - Linter should be happy now
                      formattedDate = format(localDateInstance, 'MMM d');
                      formattedTime = format(localDateInstance, 'EEEE, h:mm a');

                  } catch (e: any) { // Catch any error from parsing or conversion
                      console.error(`Error formatting date for plan ${plan.id} (UTC: ${plan.send_datetime_utc}): ${e.message}`);
                      // formattedDate and formattedTime retain their "---" default values
                  }
                  // --- End Date/Time Formatting ---

                  // --- Unique Key Generation ---
                  const uniqueKey = `${plan.source}-${plan.id}`;
                  // --- End Unique Key Generation ---

                  return (
                    // Use the unique key here
                    <div key={uniqueKey} className="relative pl-20"> {/* Added pl-20 for spacing */}
                      {/* Timeline line (vertical) */}
                      <div className="absolute left-6 top-0 bottom-0 w-1 bg-gradient-to-b from-green-600 to-teal-600 rounded-full"></div>

                      {/* Date circle - positioned relative to the line */}
                      <div className="absolute left-6 top-4 -translate-x-1/2 w-14 h-14 rounded-full bg-[#2C2F3E] border-2 border-green-500 flex items-center justify-center text-center text-xs font-medium shadow-lg shadow-green-900/30">
                        <div className="text-green-400 leading-tight">{formattedDate}</div>
                      </div>

                      {/* Content card */}
                      <div className={`rounded-lg p-6 transition-all duration-300 shadow-md hover:shadow-lg ${
                        plan.status === "scheduled"
                          ? "bg-gradient-to-br from-green-900/40 to-green-950/30 border border-green-700/50"
                          : "bg-[#1C1F2E]/80 border border-gray-700/50 backdrop-blur-sm"
                      }`}>
                        {/* Top section: Time and Status */}
                        <div className="flex justify-between items-start mb-4">
                          <div>
                             <div className="text-lg font-semibold text-gray-100">
                               {formattedTime}
                             </div>
                             <div className="text-xs text-gray-400">
                               ({timezoneDisplay.split('/')[1]?.replace('_', ' ')} Time)
                             </div>
                          </div>
                           {/* Status badge */}
                           <div className={`px-3 py-1 rounded-full text-xs font-semibold tracking-wide ${
                            plan.status === "scheduled"
                              ? "bg-green-500/20 text-green-300 border border-green-500/30"
                              : plan.status === "sent"
                              ? "bg-blue-500/20 text-blue-300 border border-blue-500/30"
                              : plan.status === "rejected"
                              ? "bg-red-500/20 text-red-300 border border-red-500/30"
                              : "bg-yellow-500/20 text-yellow-300 border border-yellow-500/30" // Default/pending
                          }`}>
                            {plan.status.toUpperCase().replace('_', ' ')}
                          </div>
                        </div>

                        {/* Main Content: Editing or Display */}
                        <div className="mb-4">
                          {editingPlan === plan.id ? (
                            // Editing View
                            <div className="space-y-3">
                              <textarea
                                value={editedContent}
                                onChange={(e) => setEditedContent(e.target.value)}
                                className="w-full p-2 text-sm text-white bg-[#2C2F3E] border border-gray-600 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                rows={3}
                                placeholder="Enter message content..."
                              />
                              <input
                                type="date"
                                value={editedDate}
                                onChange={(e) => setEditedDate(e.target.value)}
                                className="w-full p-2 text-sm text-white bg-[#2C2F3E] border border-gray-600 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                              />
                              <input
                                type="time"
                                value={editedTime}
                                onChange={(e) => setEditedTime(e.target.value)}
                                className="w-full p-2 text-sm text-white bg-[#2C2F3E] border border-gray-600 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                              />
                            </div>
                          ) : (
                            // Display View
                            <p className="text-gray-300 text-sm leading-relaxed">{plan.smsContent}</p>
                          )}
                        </div>

                        {/* Customer Info */}
                        <div className="flex items-center gap-3 text-sm border-t border-gray-700/50 pt-4">
                          <span className="text-gray-400">👤</span>
                          <span className="font-medium text-gray-200">{plan.customer_name}</span>
                          <OptInStatusBadge
                            status={plan.latest_consent_status}
                            lastUpdated={plan.latest_consent_updated}
                          />
                        </div>

                        {/* Action Buttons */}
                        <div className="flex justify-end gap-2 mt-5">
                          {editingPlan === plan.id ? (
                            // Buttons during editing
                            <>
                              <button
                                onClick={() => setEditingPlan(null)} // Cancel edit
                                className="px-3 py-1.5 text-xs font-medium bg-gray-600 hover:bg-gray-700 text-gray-100 rounded-md transition-colors"
                              >
                                Cancel
                              </button>
                              <button
                                onClick={() => handleSaveEdit(plan)}
                                className="px-3 py-1.5 text-xs font-medium bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors"
                              >
                                Save Changes
                              </button>
                            </>
                          ) : (
                            // Buttons for display mode
                            <>
                              <button
                                onClick={() => handleDelete(plan)}
                                className="px-3 py-1.5 text-xs font-medium bg-red-600/80 hover:bg-red-700 text-white rounded-md transition-colors"
                                title="Remove this message"
                              >
                                Remove
                              </button>
                              <button
                                onClick={() => handleEdit(plan)}
                                className="px-3 py-1.5 text-xs font-medium bg-blue-600/80 hover:bg-blue-700 text-white rounded-md transition-colors"
                                title="Edit message and time"
                              >
                                Edit
                              </button>
                              {/* Only show Schedule button if not already scheduled */}
                              {plan.status !== "scheduled" && (
                                <button
                                  onClick={() => handleSchedule(plan)}
                                  className="px-3 py-1.5 text-xs font-medium bg-green-600/90 hover:bg-green-700 text-white rounded-md transition-colors"
                                  title="Approve and schedule this message"
                                >
                                  Schedule
                                </button>
                              )}
                            </>
                          )}
                        </div>
                      </div> {/* End Content card */}
                    </div> // End relative container
                  );
                }) // End map over plans
              ) : (
                // Message when no plans in the group
                <div className="text-gray-500 text-center py-8 italic">
                  No messages scheduled for {group.toLowerCase()}.
                </div>
              )}
            </div> {/* End space-y-6 */}
          </div> // End group container
        ))}
      </div> {/* End max-w-6xl */}
    </div> // End main container
  );
}