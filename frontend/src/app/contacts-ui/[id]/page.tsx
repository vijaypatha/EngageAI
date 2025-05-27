"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { useParams } from "next/navigation";
import { apiClient } from "@/lib/api";
import { format } from "date-fns";
// @ts-ignore
import { zonedTimeToUtc, utcToZonedTime } from "date-fns-tz";
import { getCurrentBusiness } from "@/lib/utils";

interface RoadmapMessage {
  id: number; // Can be RoadmapMessage.id or Message.id after scheduling
  smsTiming: string; // Original timing string, might not be directly used for display if send_datetime_utc is present
  smsContent: string;
  status: string; // e.g., "pending_review", "scheduled", "sent"
  send_datetime_utc?: string; // ISO string
  // message_id?: number; // This was a thought, but backend now updates main `id` upon scheduling
}

export default function ContactEngagementPage() {
  const params = useParams();
  const customerId = params?.id as string | undefined; // Get customer ID from URL

  const [loading, setLoading] = useState(true);
  const [messages, setMessages] = useState<RoadmapMessage[]>([]);
  const [customerName, setCustomerName] = useState("");
  const [optedIn, setOptedIn] = useState<string | null>(null); // e.g., "opted_in", "opted_out", "pending"
  const [editingMessageId, setEditingMessageId] = useState<number | null>(null);
  const [editedContent, setEditedContent] = useState<string>("");
  const [editedDate, setEditedDate] = useState<string>(""); // YYYY-MM-DD
  const [editedTime, setEditedTime] = useState<string>(""); // HH:mm
  const [customerTimezone, setCustomerTimezone] = useState("America/Denver"); // Default, will be updated
  const [businessId, setBusinessId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchEngagementData = useCallback(async () => {
    if (!customerId) {
      setError("Customer ID not found in URL.");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      // Fetch customer details first
      const custRes = await apiClient.get(`/customers/${customerId}`);
      setCustomerName(custRes.data.customer_name);
      setCustomerTimezone(custRes.data.timezone || "America/Denver");

      let currentBusinessId = custRes.data.business_id;
      if (currentBusinessId) {
        setBusinessId(currentBusinessId);
      } else {
        const storedBusinessId = getCurrentBusiness(); // Fallback to localStorage
        if (storedBusinessId) {
          setBusinessId(storedBusinessId);
          currentBusinessId = storedBusinessId;
        } else {
          console.error("Business ID could not be determined for API calls.");
          setError("Business ID is missing. Cannot fetch engagement plan.");
          setLoading(false);
          return;
        }
      }

      // Fetch engagement plan for the customer
      // The endpoint /review/engagement-plan/{id} uses the customer_id as the {id}
      const planRes = await apiClient.get(`/review/engagement-plan/${customerId}`);
      if (planRes.data.engagements && Array.isArray(planRes.data.engagements)) {
        const sortedEngagements = [...planRes.data.engagements].sort((a, b) =>
          new Date(a.send_datetime_utc || 0).getTime() - new Date(b.send_datetime_utc || 0).getTime()
        );
        setMessages(sortedEngagements);
      } else {
        setMessages([]); // Ensure messages is an empty array if no engagements
      }
      setOptedIn(planRes.data.latest_consent_status);

    } catch (err: any) {
      console.error("Failed to fetch engagement data:", err);
      setError(err.response?.data?.detail || err.message || "An unknown error occurred while fetching data.");
      setMessages([]); // Clear messages on error
    } finally {
      setLoading(false);
    }
  }, [customerId]); // customerId is the dependency from useParams

  useEffect(() => {
    fetchEngagementData();
  }, [fetchEngagementData]); // fetchEngagementData is memoized by useCallback

  const regeneratePlan = async () => {
    if (!customerId || !businessId) {
      setError("Customer ID or Business ID is missing. Cannot regenerate plan.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await apiClient.post(`/ai/roadmap`, {
        customer_id: customerId,
        business_id: businessId,
        force_regenerate: true,
      });
      await fetchEngagementData(); // Refetch data after regeneration
    } catch (err: any) {
      console.error("Failed to regenerate nudge plan:", err);
      setError(err.response?.data?.detail || "Failed to regenerate plan.");
    } finally {
      setLoading(false);
    }
  };

  const handleEditClick = (msg: RoadmapMessage) => {
    setEditingMessageId(msg.id);
    setEditedContent(msg.smsContent);
    setError(null); // Clear previous errors

    try {
      const dateString = msg.send_datetime_utc || new Date().toISOString();
      const utcDate = new Date(dateString);

      if (isNaN(utcDate.getTime())) { // Check if date is valid
          console.warn("Invalid date string for editing:", msg.send_datetime_utc);
          throw new Error("Invalid date string");
      }

      setEditedDate(format(utcDate, "yyyy-MM-dd"));
      const localDate = utcToZonedTime(utcDate, customerTimezone);
      setEditedTime(format(localDate, "HH:mm"));
    } catch (e) {
      console.error("Error preparing edit form dates:", e);
      const now = new Date(); // Fallback to current date/time
      const localNow = utcToZonedTime(now, customerTimezone);
      setEditedDate(format(localNow, "yyyy-MM-dd"));
      setEditedTime(format(localNow, "HH:mm"));
      setError("Could not parse message date. Please set manually.");
    }
  };

  const handleSaveEdit = async (messageIdToSave: number) => {
    setError(null);
    const messageToEdit = messages.find((m) => m.id === messageIdToSave);
    if (!messageToEdit) {
      setError("Message to edit not found. Please refresh.");
      return;
    }

    try {
      const localDateTimeString = `${editedDate}T${editedTime}:00`;
      const localDate = new Date(localDateTimeString); // Parsed in browser's local timezone

      if (isNaN(localDate.getTime())) {
        setError("Invalid date or time entered for saving.");
        return;
      }
      
      const utcDateISOString = zonedTimeToUtc(localDate, customerTimezone).toISOString();

      // Determine source: if status is "scheduled", it means it's a Message record. Otherwise, it's a RoadmapMessage.
      // The `id` field in the `messages` state should already be the correct ID for the API call
      // (RoadmapMessage.id for unscheduled, Message.id for scheduled).
      const source = messageToEdit.status === "scheduled" ? "scheduled" : "roadmap";
      const idForApi = messageToEdit.id;

      await apiClient.put(`/roadmap-workflow/update-time/${idForApi}?source=${source}`, {
        smsContent: editedContent,
        send_datetime_utc: utcDateISOString,
      });

      setMessages((prevMessages) =>
        prevMessages
          .map((m) =>
            m.id === messageIdToSave
              ? { ...m, smsContent: editedContent, send_datetime_utc: utcDateISOString }
              : m
          )
          .sort((a, b) => new Date(a.send_datetime_utc || 0).getTime() - new Date(b.send_datetime_utc || 0).getTime())
      );
      setEditingMessageId(null);
    } catch (err: any) {
      console.error("Failed to save edited message:", err);
      setError(err.response?.data?.detail || "Failed to save changes.");
    }
  };

  const handleCancelEdit = () => {
    setEditingMessageId(null);
    setError(null);
  };

  const handleApprove = async (roadmapMessageIdToApprove: number) => {
    setError(null);
    try {
      // API expects the RoadmapMessage.id for scheduling
      const res = await apiClient.put(`/roadmap-workflow/${roadmapMessageIdToApprove}/schedule`);
      
      const newScheduledMessageId = res.data.message_id; // This is the ID of the new Message record
      const backendResponseMessageDetails = res.data.message; // Contains updated details

      if (!newScheduledMessageId) {
        throw new Error("Scheduling response did not include a 'message_id'.");
      }

      setMessages(prev =>
        prev
          .map(msg => {
            if (msg.id === roadmapMessageIdToApprove) {
              // This roadmap message is now scheduled. Update its ID to the new Message.id,
              // and its status, and other details from the backend response.
              return { 
                ...msg, 
                id: newScheduledMessageId, // CRITICAL: Update ID to the new Message table ID
                status: backendResponseMessageDetails?.status || "scheduled",
                smsContent: backendResponseMessageDetails?.smsContent || msg.smsContent,
                send_datetime_utc: backendResponseMessageDetails?.send_datetime_utc || msg.send_datetime_utc,
              };
            }
            return msg;
          })
          .sort((a, b) => new Date(a.send_datetime_utc || 0).getTime() - new Date(b.send_datetime_utc || 0).getTime())
      );
    } catch (err: any) {
      console.error("Failed to schedule message:", err);
      setError(err.response?.data?.detail || err.message || "Failed to schedule message.");
    }
  };

  const handleDelete = async (messageIdToDelete: number) => {
    setError(null);
    const message = messages.find(m => m.id === messageIdToDelete);
    if (!message) {
      setError("Message not found. It might have been already deleted.");
      return;
    }
    
    // The `id` in the `message` object is already the correct ID for the API call
    // (RoadmapMessage.id for unscheduled, Message.id for scheduled).
    // The `status` determines the `source` parameter.
    const source = message.status === "scheduled" ? "scheduled" : "roadmap";
    const idForApi = message.id;

    const originalMessages = [...messages]; // Keep a copy for potential rollback
    setMessages(prev => prev.filter(msg => msg.id !== messageIdToDelete)); // Optimistic update

    try {
      await apiClient.delete(`/roadmap-workflow/${idForApi}?source=${source}`);
      // Deletion successful, optimistic update stands.
    } catch (err: any) {
      console.error("Failed to delete message:", err);
      setError(err.response?.data?.detail || "Failed to delete message.");
      setMessages(originalMessages); // Rollback optimistic update
      // Consider a full refetch if state becomes too complex to manage with rollbacks:
      // await fetchEngagementData(); 
    }
  };

  const groupedMessages = useMemo(() => {
    const grouped: Record<string, RoadmapMessage[]> = {};
    // Ensure messages is an array and not undefined/null before processing
    if (!Array.isArray(messages) || messages.length === 0) {
      return grouped; // Return empty object if no messages
    }

    messages.forEach((msg) => {
      try {
        const dateObj = msg.send_datetime_utc ? new Date(msg.send_datetime_utc) : null;
        // Use "MMM yyyy" for grouping to include the year, handles undated items
        const groupKey = dateObj && !isNaN(dateObj.getTime()) ? format(dateObj, "MMM yyyy") : "Undated";
        
        if (!grouped[groupKey]) {
          grouped[groupKey] = [];
        }
        grouped[groupKey].push(msg);
      } catch (e) {
        console.warn("Error processing message for grouping:", msg, e);
        // Optionally, add to a specific "Errored" group or skip
        if (!grouped["Errored Dates"]) grouped["Errored Dates"] = [];
        grouped["Errored Dates"].push(msg);
      }
    });
    return grouped;
  }, [messages]); // Dependency: messages state

  // Helper to generate a unique key for list items, especially after ID changes on schedule
  const getMessageKey = (msg: RoadmapMessage): string => {
    // The `msg.id` should be unique enough if backend correctly provides the new Message.id
    // `msg.status` can differentiate if there's a rare scenario of ID collision before/after scheduling (unlikely with UUIDs/sequences)
    return `${msg.status}-${msg.id}`;
  };


  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6 bg-gradient-to-br from-slate-900 to-slate-800 text-white min-h-screen font-sans">
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold tracking-tight">📬 Nudge Plan: {customerName}</h1>
        <div className="flex items-center space-x-4">
            <span className={`text-sm font-medium px-3 py-1 rounded-full ${
                optedIn === "opted_in" ? "bg-green-500/20 text-green-300 border border-green-500/30" :
                optedIn === "opted_out" ? "bg-red-500/20 text-red-300 border border-red-500/30" :
                "bg-yellow-500/20 text-yellow-300 border border-yellow-500/30"
            }`}>
            {optedIn === "opted_in" ? "✅ Opted In" :
             optedIn === "opted_out" ? "❌ Opted Out" :
             "⏳ Waiting/Unknown"}
            </span>
            <button
                onClick={regeneratePlan}
                disabled={loading}
                className="bg-purple-600 hover:bg-purple-700 text-white font-semibold py-2 px-4 rounded-lg shadow-md hover:shadow-purple-500/30 transition duration-300 ease-in-out disabled:opacity-60 disabled:cursor-not-allowed flex items-center space-x-2"
            >
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
                    <path fillRule="evenodd" d="M15.312 5.312a1 1 0 00-1.414 0L10 9.172 6.102 5.273a1 1 0 00-1.414 1.414L8.828 10l-3.89 3.89a1 1 0 101.415 1.414L10 11.172l3.89 3.89a1 1 0 001.414-1.415L11.172 10l3.89-3.89a1 1 0 000-1.414z" clipRule="evenodd" transform="rotate(45 10 10) scale(0.8)" />
                    <path d="M10 2.5a7.5 7.5 0 11-7.5 7.5c0 .414.336.75.75.75s.75-.336.75-.75a6 6 0 106-6c.414 0 .75-.336.75-.75s-.336-.75-.75-.75z" />
                 </svg>
                <span>Regenerate Plan</span>
            </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-300 px-4 py-3 rounded-lg relative mb-6" role="alert">
            <strong className="font-semibold">Error: </strong>
            <span className="block sm:inline">{error}</span>
            <button onClick={() => setError(null)} className="absolute top-0 bottom-0 right-0 px-4 py-3 text-red-300 hover:text-red-100">
                <svg className="fill-current h-6 w-6" role="button" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><title>Close</title><path d="M14.348 14.849a1.2 1.2 0 0 1-1.697 0L10 11.819l-2.651 3.029a1.2 1.2 0 1 1-1.697-1.697l2.758-3.15-2.759-3.152a1.2 1.2 0 1 1 1.697-1.697L10 8.183l2.651-3.031a1.2 1.2 0 1 1 1.697 1.697l-2.758 3.152 2.758 3.15a1.2 1.2 0 0 1 0 1.698z"/></svg>
            </button>
        </div>
      )}

      {loading ? (
        <div className="flex flex-col items-center justify-center mt-20 space-y-4">
          <svg className="animate-spin h-10 w-10 text-purple-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <p className="text-lg font-medium text-slate-400">Loading engagement plan...</p>
        </div>
      ) : Object.keys(groupedMessages).length === 0 && !error ? ( // Only show "No messages" if no error
        <div className="text-center py-10">
            <svg xmlns="http://www.w3.org/2000/svg" className="mx-auto h-12 w-12 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 10h.01M15 10h.01M9 14h.01M15 14h.01" />
            </svg>
            <p className="mt-4 text-slate-400 italic">No messages planned currently.</p>
            <p className="text-sm text-slate-500">Try regenerating the roadmap or check back later.</p>
        </div>
      ) : (
        Object.entries(groupedMessages).map(([monthYear, msgsInGroup]) => (
          <div key={monthYear} className="mb-10">
            <h2 className="text-2xl font-semibold text-slate-200 border-b border-slate-700 pb-3 mb-6">{monthYear}</h2>
            <div className="relative border-l-2 border-purple-500/50 ml-4 sm:ml-6"> {/* Adjusted margin for timeline */}
              {msgsInGroup.map((msg, index) => {
                const utcDate = msg.send_datetime_utc ? new Date(msg.send_datetime_utc) : null;
                let localDateDisplay = "N/A";
                let weekday = "";
                let time = "";
                let monthAbbr = "---";
                let dayNum = "--";

                if (utcDate && !isNaN(utcDate.getTime())) {
                    try {
                        const localDateInstance = utcToZonedTime(utcDate, customerTimezone);
                        localDateDisplay = format(localDateInstance, "MMM d, yyyy");
                        weekday = format(localDateInstance, "EEEE");
                        time = format(localDateInstance, "h:mm a");
                        monthAbbr = format(localDateInstance, "LLL").toUpperCase();
                        dayNum = format(localDateInstance, "d");
                    } catch (e) {
                        console.warn("Error formatting date for display:", msg.send_datetime_utc, e);
                    }
                }
                
                return (
                  <div key={getMessageKey(msg)} className={`relative pl-10 pb-10 ${index === msgsInGroup.length - 1 ? 'pb-0' : ''}`}> {/* Remove bottom padding for last item */}
                    {/* Timeline Dot */}
                    <div className="absolute -left-[calc(0.75rem+1px)] top-0 flex items-center justify-center"> {/* Adjusted for 1.5rem dot */}
                        <div className="h-6 w-6 rounded-full bg-purple-500 border-2 border-slate-800 ring-2 ring-purple-500/50 flex flex-col items-center justify-center text-white font-bold text-[0.6rem] shadow-lg">
                            <span>{monthAbbr}</span>
                            <span className="text-xs">{dayNum}</span>
                        </div>
                    </div>
                    
                    {/* Card */}
                    <div
                      className={`ml-6 rounded-xl shadow-xl p-5 transition-all duration-300 hover:shadow-purple-500/20 ${
                        msg.status === "scheduled"
                          ? "bg-green-600/10 border border-green-500/30"
                          : msg.status === "sent"
                          ? "bg-blue-600/10 border border-blue-500/30"
                          : "bg-slate-700/50 border border-slate-600/70 backdrop-blur-sm"
                      }`}
                    >
                      <div className="flex justify-between items-start mb-3">
                        <div>
                            <p className="text-lg font-semibold text-slate-100">
                            {weekday ? `${weekday}, ${time}` : localDateDisplay}
                            </p>
                            <p className="text-xs text-slate-400">
                                ({customerTimezone.split('/')[1]?.replace('_', ' ') || 'Local Time'})
                            </p>
                        </div>
                        <span
                          className={`text-xs font-semibold uppercase px-3 py-1 rounded-full tracking-wider ${
                            msg.status === "scheduled"
                              ? "bg-green-500/80 text-white"
                              : msg.status === "sent"
                              ? "bg-blue-500/80 text-white"
                              : "bg-yellow-500/80 text-slate-900"
                          }`}
                        >
                          {msg.status.replace("_", " ")}
                        </span>
                      </div>

                      {editingMessageId === msg.id ? (
                        <div className="space-y-3 mt-2">
                          <textarea
                            value={editedContent}
                            onChange={(e) => setEditedContent(e.target.value)}
                            className="w-full p-3 text-sm text-slate-100 bg-slate-800 border border-slate-600 rounded-md focus:ring-2 focus:ring-purple-500 focus:border-purple-500 transition-colors"
                            rows={4}
                          />
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <input
                                type="date"
                                value={editedDate}
                                onChange={(e) => setEditedDate(e.target.value)}
                                className="w-full p-3 text-sm text-slate-100 bg-slate-800 border border-slate-600 rounded-md focus:ring-2 focus:ring-purple-500 focus:border-purple-500 transition-colors"
                            />
                            <input
                                type="time"
                                value={editedTime}
                                onChange={(e) => setEditedTime(e.target.value)}
                                className="w-full p-3 text-sm text-slate-100 bg-slate-800 border border-slate-600 rounded-md focus:ring-2 focus:ring-purple-500 focus:border-purple-500 transition-colors"
                            />
                          </div>
                          <div className="flex justify-end gap-3 pt-2">
                            <button
                              onClick={handleCancelEdit}
                              className="text-sm px-4 py-2 bg-slate-600 hover:bg-slate-500 rounded-md text-slate-100 shadow transition-colors"
                            >
                              Cancel
                            </button>
                            <button
                              onClick={() => handleSaveEdit(msg.id)}
                              className="text-sm px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-md text-white shadow-md transition-colors"
                            >
                              Save Changes
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="mt-1">
                          <p className="text-slate-300 text-sm leading-relaxed mb-4 whitespace-pre-wrap">{msg.smsContent}</p>
                          <div className="flex justify-end gap-2 items-center">
                            <button
                              onClick={() => handleDelete(msg.id)}
                              title="Remove this message"
                              className="text-sm px-3 py-1.5 bg-red-700/80 hover:bg-red-600 rounded-md text-white shadow transition-colors flex items-center space-x-1.5"
                            >
                               <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4"><path fillRule="evenodd" d="M8.75 1A2.75 2.75 0 006 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 10.23 1.482l.149-.022.841 10.518A2.75 2.75 0 007.596 19h4.807a2.75 2.75 0 002.742-2.53l.841-10.52.149.023a.75.75 0 00.23-1.482A41.03 41.03 0 0014 4.193v-.443A2.75 2.75 0 0011.25 1h-2.5zM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4zM8.58 7.72a.75.75 0 00-1.5.06l.3 7.5a.75.75 0 101.5-.06l-.3-7.5zm4.34.06a.75.75 0 10-1.5-.06l-.3 7.5a.75.75 0 101.5.06l.3-7.5z" clipRule="evenodd" /></svg>
                                <span>Remove</span>
                            </button>
                            <button
                              onClick={() => handleEditClick(msg)}
                              title="Edit message content and time"
                              className="text-sm px-3 py-1.5 bg-blue-600/80 hover:bg-blue-500 rounded-md text-white shadow transition-colors flex items-center space-x-1.5"
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4"><path d="M5.433 13.917l1.262-3.155A4 4 0 017.58 9.42l6.92-6.918a2.121 2.121 0 013 3l-6.92 6.918c-.383.383-.84.685-1.343.886l-3.154 1.262a.5.5 0 01-.65-.65z" /><path d="M3.5 5.75c0-.69.56-1.25 1.25-1.25H10A.75.75 0 0010 3H4.75A2.75 2.75 0 002 5.75v9.5A2.75 2.75 0 004.75 18h9.5A2.75 2.75 0 0017 15.25V10a.75.75 0 00-1.5 0v5.25c0 .69-.56 1.25-1.25 1.25h-9.5c-.69 0-1.25-.56-1.25-1.25v-9.5z" /></svg>
                                <span>Edit</span>
                            </button>
                            {msg.status !== "scheduled" && msg.status !== "sent" && (
                              <button
                                onClick={() => handleApprove(msg.id)} // msg.id here is RoadmapMessage.id
                                disabled={optedIn === "opted_out" || optedIn === "declined"}
                                title={optedIn === "opted_out" || optedIn === "declined" ? "Customer opted out" : "Approve and schedule this message"}
                                className={`text-sm px-3 py-1.5 rounded-md text-white shadow transition-colors flex items-center space-x-1.5 ${
                                  (optedIn === "opted_out" || optedIn === "declined")
                                    ? 'bg-slate-500 cursor-not-allowed'
                                    : 'bg-purple-600 hover:bg-purple-500'
                                }`}
                              >
                                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4"><path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" /></svg>
                                <span>Schedule</span>
                              </button>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
