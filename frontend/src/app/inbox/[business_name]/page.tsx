// frontend/src/app/inbox/[business_name]/page.tsx
"use client";

import { useEffect, useState, useMemo, useRef, useCallback } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { apiClient } from "@/lib/api";
import {
  Clock,
  SendHorizonal,
  MessageSquare,
  Check,
  AlertCircle,
  Trash2,
  Edit3,
  CheckCheck,
  User,
  Phone,
  MessageCircleIcon,
  Zap,
  ClipboardEdit,
  Settings2,
  CalendarPlus,
  CalendarCheck,
  Bell,
  XCircle,
  Filter as FilterIcon,
  ChevronDown,
  TrafficCone,
  RefreshCw,
  SidebarOpen,
  SidebarClose,
  AlertTriangle,
} from "lucide-react";
import clsx from "clsx";
import { format, isValid, parseISO, isFuture, formatISO, isToday, differenceInDays, addDays } from 'date-fns';
import { AppointmentNudgeAssistCard } from "@/components/AppointmentNudgeAssistCard";
import { Button } from "@/components/ui/button";

// --- Enums & Interfaces ---

enum AppointmentRequestStatusEnum {
  PENDING_OWNER_ACTION = "pending_owner_action",
  BUSINESS_INITIATED_PENDING_CUSTOMER_REPLY = "business_initiated_pending_customer_reply",
  CUSTOMER_CONFIRMED_PENDING_OWNER_APPROVAL = "customer_confirmed_pending_owner_approval",
  CUSTOMER_REQUESTED_RESCHEDULE = "customer_requested_reschedule",
  CONFIRMED_BY_OWNER = "confirmed_by_owner",
  OWNER_PROPOSED_RESCHEDULE = "owner_proposed_reschedule",
  DECLINED_BY_OWNER = "declined_by_owner",
  CUSTOMER_DECLINED_PROPOSAL = "customer_declined_proposal",
  CANCELLED_BY_CUSTOMER = "cancelled_by_customer",
  CANCELLED_BY_OWNER = "cancelled_by_owner",
  COMPLETED = "completed",
  NO_SHOW = "no_show",
}

enum AppointmentActionIntentEnum {
    OWNER_ACTION_CONFIRM = "owner_action_confirm",
    OWNER_ACTION_SUGGEST_RESCHEDULE = "owner_action_suggest_reschedule",
    OWNER_ACTION_DECLINE = "owner_action_decline",
}

const formatSlotInBusinessTimezone = (slotUtc: string, timezone: string | undefined): string => {
  if (!slotUtc) return "N/A";
  try {
    const date = parseISO(slotUtc);
    const options: Intl.DateTimeFormatOptions = {
      weekday: 'short', month: 'short', day: 'numeric',
      hour: 'numeric', minute: '2-digit', hour12: true,
    };
    if (timezone) {
      try {
         return new Intl.DateTimeFormat('en-US', {...options, timeZone: timezone }).format(date);
      } catch (e) {
        console.warn("Invalid timezone for Intl.DateTimeFormat, falling back:", timezone, e);
        return format(date, "eee, MMM d 'at' p");
      }
    }
    return format(date, "eee, MMM d 'at' p");
  } catch (error) {
    console.error("Error formatting date:", error);
    return "Invalid Date";
  }
};

interface AppointmentActionContext {
  customer_name?: string | null;
  original_customer_request_text?: string | null;
  parsed_requested_time_text?: string | null;
  owner_proposed_new_time_text?: string | null;
  owner_reason_for_action?: string | null;
}

interface AppointmentActionDraftRequestPayload {
  action_type: AppointmentActionIntentEnum;
  context?: AppointmentActionContext | null;
}

interface AppointmentRequestStatusUpdateByOwnerPayload {
  new_status: AppointmentRequestStatusEnum;
  sms_message_body: string;
  send_sms_to_customer: boolean;
  owner_suggested_datetime_utc_iso?: string | null;
  owner_suggested_time_text?: string | null;
  resolution_notes?: string | null;
}

interface MessageUpdatePayload {
  content?: string | null;
  scheduled_send_at?: string | null;
  status?: string | null;
}

interface CustomerData {
  id: number;
  customer_name: string | null;
  phone: string;
  sms_opt_in_status: string;
  latest_consent_status?: string | null;
  latest_consent_updated?: string | null;
  timezone?: string | null;
  business?: {
    timezone?: string | null;
  } | null;
}

interface AppointmentRequest {
  id: number;
  business_id: number;
  customer_id: number;
  original_message_text: string | null;
  parsed_requested_time_text: string | null;
  parsed_requested_datetime_utc: string | null;
  status: AppointmentRequestStatusEnum;
  source: string;
  confirmed_datetime_utc: string | null;
  owner_suggested_time_text: string | null;
  owner_suggested_datetime_utc: string | null;
  details: string | null;
  created_at: string;
  updated_at: string;
}

interface InboxConversationItem {
  customer_id: number;
  customer_name: string;
  last_message_content: string;
  last_message_timestamp?: string | null;
  last_message_type?: string | null;
  last_message_status?: string | null;
  conversation_id?: string | null;
  latest_appointment_request_id?: number | null;
  latest_appointment_request_status?: AppointmentRequestStatusEnum | null;
  latest_appointment_request_datetime_utc?: string | null;
  latest_appointment_request_time_text?: string | null;
}

interface ApiMessage {
  id: string | number;
  text: string;
  type: string; 
  status?: string; 
  timestamp: string;
  direction?: "inbound" | "outbound"; 
  is_hidden?: boolean; 
  sender_name?: string; 
  source?: string; 
}

interface TimelineEntry {
  id: string | number;
  type: "customer" | "sent" | "ai_draft" | "outbound_ai_reply" | "system_notification" | "appointment_related" | "other";
  content: string;
  raw_content?: string;
  timestamp: string | null;
  customer_id?: number;
  is_hidden?: boolean;
  status?: string;
  source?: string;
  sender_name?: string;
  is_faq_autopilot?: boolean;
  is_ai_initial_reply?: boolean;
  is_ai_draft_for_review?: boolean;
  is_pending_scheduled?: boolean;
  scheduled_message_type?: "reminder" | "thank_you" | "other";
  appointment_lifecycle_tag?: string;
}

interface ActiveCustomerData {
  customer: CustomerData;
  messages: ApiMessage[];
  conversation_id: string;
  latest_appointment_request?: AppointmentRequest | null;
  draft_reply_for_appointment?: string | null;
}

interface AiSuggestedSlot {
  slot_utc: string;
  status_message: string;
  isPrimaryConfirmation?: boolean; // Optional flag to identify the primary slot
}

type FilterOption = "all" | "needs_action_appointments" | "upcoming_appointments" | "no_appointment_history";
type OptInStatus = "opted_in" | "opted_out" | "pending" | "waiting" | "error";

// --- Helper Functions ---
const getUIConsentStatus = (customer: CustomerData | null | undefined): OptInStatus => {
  if (!customer) return "waiting";
  const statusToEvaluate = customer.latest_consent_status;
  if (!statusToEvaluate) {
    return "waiting";
  }
  switch (statusToEvaluate) {
    case "opted_in": return "opted_in";
    case "opted_out": return "opted_out";
    case "pending": return "pending";
    case "pending_confirmation": return "pending";
    case "declined": return "opted_out";
    case "waiting": return "waiting";
    default:
      console.warn(`[InboxPage] Unknown latest_consent_status: '${statusToEvaluate}' for customer ${customer.id}. Original sms_opt_in_status: '${customer.sms_opt_in_status}'`);
      return "error";
  }
};

const formatDateShort = (dateString: string | null | undefined): string => {
  if (!dateString) return "";
  const date = parseISO(dateString);
  if (!isValid(date)) return "Invalid date";
  try {
    const now = new Date();
    if (isToday(date)) return format(date, "p"); 
    if (differenceInDays(now, date) < 7 && date < now) return format(date, "eee"); 
    return format(date, "MMM d"); 
  } catch (e) { console.error("Error formatting date (short):", dateString, e); return "Invalid date"; }
};

const formatMessageTimestamp = (dateString: string | null | undefined): string => {
  if (!dateString) return "";
  const date = parseISO(dateString);
  return isValid(date) ? format(date, "MMM d, p") : ""; 
};

const formatForDateTimeLocal = (isoString: string | null | undefined): string => {
  if (!isoString) return "";
  const date = parseISO(isoString);
  return isValid(date) ? format(date, "yyyy-MM-dd'T'HH:mm") : "";
};

export default function InboxPage() {
  const { business_name } = useParams<{ business_name: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();

  const [businessId, setBusinessId] = useState<number | null>(null);
  const [businessSlug, setBusinessSlug] = useState<string>("");
  const [businessTimezone, setBusinessTimezone] = useState<string | undefined>("UTC");

  const [isLoadingConversations, setIsLoadingConversations] = useState(true);
  const [isLoadingChat, setIsLoadingChat] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const [customerSummaries, setCustomerSummaries] = useState<InboxConversationItem[]>([]);
  const [activeCustomerId, setActiveCustomerId] = useState<number | null>(null);
  const [filterOption, setFilterOption] = useState<FilterOption>("all");
  const [showMobileDrawer, setShowMobileDrawer] = useState(false);

  const [activeCustomerData, setActiveCustomerData] = useState<ActiveCustomerData | null>(null);
  const [timelineEntries, setTimelineEntries] = useState<TimelineEntry[]>([]);
  const [newMessage, setNewMessage] = useState("");
  const [editingAiDraftOriginalContent, setEditingAiDraftOriginalContent] = useState<string | null>(null);
  const [selectedAiDraftIdForEdit, setSelectedAiDraftIdForEdit] = useState<string | number | null>(null);

  const [isSending, setIsSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);

  const [showEditScheduledModal, setShowEditScheduledModal] = useState(false);
  const [editingScheduledMessage, setEditingScheduledMessage] = useState<TimelineEntry | null>(null);
  const [editedScheduledContent, setEditedScheduledContent] = useState("");
  const [editedScheduledTimeISO, setEditedScheduledTimeISO] = useState("");
  const [isUpdatingScheduled, setIsUpdatingScheduled] = useState(false);

  const [aiSuggestedSlots, setAiSuggestedSlots] = useState<AiSuggestedSlot[]>([]);
  const [isLoadingAiSuggestions, setIsLoadingAiSuggestions] = useState(false);
  const [aiSuggestionsError, setAiSuggestionsError] = useState<string | null>(null);
  
  const [nudgeCardActionContext, setNudgeCardActionContext] = useState<{
    intent: AppointmentActionIntentEnum;
    slot?: AiSuggestedSlot; 
    appointmentId: number;
  } | null>(null);
  const [isProcessingNudgeAction, setIsProcessingNudgeAction] = useState(false);
  const [showNudgeCard, setShowNudgeCard] = useState(true);

  const chatContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const currentCustomerConsentStatus = useMemo(() => {
    if (activeCustomerData?.customer) {
      return getUIConsentStatus(activeCustomerData.customer);
    }
    return "waiting"; 
  }, [activeCustomerData?.customer]);
  
  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [timelineEntries]);

  useEffect(() => {
    const initialize = async () => {
      if (!business_name || typeof business_name !== 'string') {
        setFetchError("Business identifier missing."); setIsLoadingConversations(false); return;
      }
      setBusinessSlug(business_name); setIsLoadingConversations(true); setFetchError(null);
      try {
        const bizRes = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
        const id = bizRes.data?.business_id;
        if (!id) throw new Error("Business ID not found.");
        setBusinessId(id);
        const tzRes = await apiClient.get(`/business-profile/${id}/timezone`);
        setBusinessTimezone(tzRes.data?.timezone || "UTC");
      } catch (error: any) {
        setFetchError(error.message || "Failed to load business data."); setIsLoadingConversations(false);
      }
    };
    initialize();
  }, [business_name]);

  const fetchCustomerSummaries = useCallback(async (bId: number, currentFilter: FilterOption, showLoader: boolean = true) => {
    if (showLoader) setIsLoadingConversations(true); setFetchError(null);
    try {
      let endpoint = `/conversations/inbox`;
      const params = new URLSearchParams();
      if (currentFilter === "needs_action_appointments") {
        params.append("appointment_status", AppointmentRequestStatusEnum.PENDING_OWNER_ACTION);
        params.append("appointment_status", AppointmentRequestStatusEnum.CUSTOMER_REQUESTED_RESCHEDULE);
        params.append("appointment_status", AppointmentRequestStatusEnum.CUSTOMER_CONFIRMED_PENDING_OWNER_APPROVAL);
      } else if (currentFilter === "upcoming_appointments") {
        params.append("appointment_status", AppointmentRequestStatusEnum.CONFIRMED_BY_OWNER);
      } else if (currentFilter === "no_appointment_history") {
        params.append("no_appointment_history", "true");
      }
      
      const queryString = params.toString();
      if (queryString) endpoint += `?${queryString}`;

      const res = await apiClient.get(endpoint);
      const processedSummaries = (res.data.conversations || []).map((cs: InboxConversationItem) => {
        let displayLastMessage = cs.last_message_content;
        if (typeof cs.last_message_content === 'string' && cs.last_message_content.startsWith('{') && cs.last_message_content.endsWith('}')) {
          try {
            const parsed = JSON.parse(cs.last_message_content);
            if (parsed && typeof parsed.text === 'string') {
              displayLastMessage = parsed.text;
            }
          } catch (e) { /* Keep raw if not parsable */ }
        }
        return { ...cs, last_message_content: displayLastMessage };
      });
      setCustomerSummaries(processedSummaries);
    } catch (error: any) {
      setFetchError("Failed to load conversations: " + error.message); setCustomerSummaries([]);
    } finally {
      if (showLoader) setIsLoadingConversations(false);
    }
  }, []);

  useEffect(() => {
    if (businessId) {
      fetchCustomerSummaries(businessId, filterOption);
      const intervalId = setInterval(() => {
        if (document.visibilityState === 'visible' && businessId) {
          fetchCustomerSummaries(businessId, filterOption, false);
        }
      }, 5000);
      return () => clearInterval(intervalId);
    }
  }, [businessId, filterOption, fetchCustomerSummaries]);

  const fetchActiveCustomerData = useCallback(async (customerId: number, bId: number) => {
    setIsLoadingChat(true); setFetchError(null); setShowNudgeCard(true);
    try {
      const res = await apiClient.get(`/conversations/customer/${customerId}`);
      setActiveCustomerData(res.data as ActiveCustomerData);
      setSendError(null); setNewMessage(""); 
      setSelectedAiDraftIdForEdit(null); setEditingAiDraftOriginalContent(null);
      setNudgeCardActionContext(null); 
    } catch (error: any) {
      setFetchError(`Failed to load chat for customer ${customerId}: ` + error.message); setActiveCustomerData(null);
    } finally { setIsLoadingChat(false); }
  }, []);

  useEffect(() => {
    const urlCustomerIdStr = searchParams.get('activeCustomer');
    if (urlCustomerIdStr) {
      const urlCustomerId = parseInt(urlCustomerIdStr, 10);
      if (activeCustomerId !== urlCustomerId) setActiveCustomerId(urlCustomerId);
    } else if (customerSummaries.length > 0 && !activeCustomerId) {
      // No auto-selection
    }
  }, [searchParams, customerSummaries, activeCustomerId]);

  useEffect(() => {
    if (activeCustomerId && businessId) {
      fetchActiveCustomerData(activeCustomerId, businessId);
      const currentQueryParam = searchParams.get('activeCustomer');
      if (String(activeCustomerId) !== currentQueryParam) {
        router.replace(`/inbox/${businessSlug}?activeCustomer=${activeCustomerId}`, { scroll: false });
      }
    } else if (!activeCustomerId && businessSlug && searchParams.get('activeCustomer')) {
       setActiveCustomerData(null);
       router.replace(`/inbox/${businessSlug}`, { scroll: false });
    }
  }, [activeCustomerId, businessId, fetchActiveCustomerData, businessSlug, router]);

  useEffect(() => {
    if (!activeCustomerData?.messages) {
      setTimelineEntries([]); 
      return;
    }
    const newTimelineEntries: TimelineEntry[] = activeCustomerData.messages
      .filter(msg => !msg.is_hidden || (msg.type === "ai_draft" && msg.source === "system_ai_draft" && !msg.is_hidden))
      .map((apiMsg: ApiMessage): TimelineEntry => {
        let processedContent = apiMsg.text || "[No content]"; 
        const rawApiText = apiMsg.text; 
        let isFaqFlagFromSourceOrContent = apiMsg.source === "system_faq_autopilot" || apiMsg.source === "faq_autopilot";
        if (typeof apiMsg.text === 'string' && apiMsg.text.startsWith('{') && apiMsg.text.endsWith('}')) {
          try {
            const parsedJson = JSON.parse(apiMsg.text);
            if (parsedJson && typeof parsedJson.text === 'string') {
              processedContent = parsedJson.text; 
            }
            if (parsedJson && typeof parsedJson.is_faq_answer === 'boolean' && parsedJson.is_faq_answer) {
              isFaqFlagFromSourceOrContent = true; 
            }
          } catch (e) { /* Not valid JSON, proceed with raw text */ }
        }
        let uiType: TimelineEntry["type"] = "other"; 
        let isAiInitial = apiMsg.source === "system_appointment_autopilot" || apiMsg.source === "ai_initial_reply";
        let isDraftForReview = false; 
        let isPendingSched = false; 
        let schedMsgType: TimelineEntry["scheduled_message_type"] = "other"; 
        let apptLifecycleTag = ""; 
        const msgTypeForLogic = apiMsg.type; 
        if (apiMsg.type === "inbound") { 
            uiType = "customer";
        } else if (apiMsg.type === "outbound" || apiMsg.status === "sent" || apiMsg.type === "sent") { 
            uiType = "sent";
        } else if (apiMsg.type === "outbound_ai_reply") { 
             uiType = "outbound_ai_reply";
        } else if (apiMsg.type === "ai_draft" && 
          (apiMsg.source === "ai_response_engagement" || 
           apiMsg.source === "system_ai_draft" ||
           apiMsg.source === "customer_sms_reply_engagement")) { // Added "customer_sms_reply_engagement"
            uiType = "ai_draft"; isDraftForReview = true;
        }else if (apiMsg.type === "system_notification") { 
             uiType = "system_notification";
        }
        if (msgTypeForLogic === "appointment_proposal" && apiMsg.status === "sent") {
            uiType = "appointment_related"; apptLifecycleTag = "📅 Proposal Sent";
        } else if (msgTypeForLogic === "appointment_confirmation" && apiMsg.status === "sent") {
            uiType = "appointment_related"; apptLifecycleTag = "✅ Confirmation Sent";
        } else if (msgTypeForLogic === "appointment_reminder") { 
            uiType = "appointment_related";
            if (apiMsg.status === "scheduled") { 
                isPendingSched = true; schedMsgType = "reminder";
            } else if (apiMsg.status === "sent") { 
                 apptLifecycleTag = "🔔 Reminder Sent";
            }
        } else if (msgTypeForLogic === "appointment_thank_you") { 
            uiType = "appointment_related";
            if (apiMsg.status === "scheduled") { 
                isPendingSched = true; schedMsgType = "thank_you";
            } else if (apiMsg.status === "sent") { 
                apptLifecycleTag = "🤝 Thank You Sent";
            }
        }
        return {
          id: String(apiMsg.id), type: uiType, content: processedContent, raw_content: rawApiText, timestamp: apiMsg.timestamp, customer_id: activeCustomerData.customer.id, is_hidden: apiMsg.is_hidden || false, status: apiMsg.status, source: apiMsg.source, sender_name: apiMsg.sender_name, is_faq_autopilot: isFaqFlagFromSourceOrContent, is_ai_initial_reply: isAiInitial, is_ai_draft_for_review: isDraftForReview, is_pending_scheduled: isPendingSched, scheduled_message_type: schedMsgType, appointment_lifecycle_tag: apptLifecycleTag, 
        };
      })
      .sort((a, b) => { 
        const timeA = a.timestamp ? parseISO(a.timestamp).getTime() : 0;
        const timeB = b.timestamp ? parseISO(b.timestamp).getTime() : 0;
        return timeA - timeB;
      });
    setTimelineEntries(newTimelineEntries);
  }, [activeCustomerData]); 
  
  const currentCustomer = activeCustomerData?.customer;
  const actionableAppointment = useMemo(() => {
    if (!activeCustomerData?.latest_appointment_request) return null;
    const status = activeCustomerData.latest_appointment_request.status;
    if (status === AppointmentRequestStatusEnum.PENDING_OWNER_ACTION || status === AppointmentRequestStatusEnum.CUSTOMER_REQUESTED_RESCHEDULE || status === AppointmentRequestStatusEnum.CUSTOMER_CONFIRMED_PENDING_OWNER_APPROVAL) {
      return activeCustomerData.latest_appointment_request;
    } return null;
  }, [activeCustomerData]);

  const actionableAppointmentId = useMemo(() => actionableAppointment ? actionableAppointment.id : null, [actionableAppointment]);

  const fetchAiSlotSuggestions = useCallback(async (requestId: number, currentBusinessId: number) => {
    if (!requestId || !currentBusinessId) {
      setAiSuggestionsError("Missing request ID or business ID for fetching AI suggestions.");
      return;
    }
    setIsLoadingAiSuggestions(true);
    setAiSuggestionsError(null);
    setAiSuggestedSlots([]); 
    try {
      // Pass current appointment status and confirmed_utc to backend if available
      const params = new URLSearchParams();
      if (actionableAppointment) {
        params.append("original_status", actionableAppointment.status);
        if (actionableAppointment.confirmed_datetime_utc) {
          params.append("original_confirmed_utc", actionableAppointment.confirmed_datetime_utc);
        }
        if (actionableAppointment.parsed_requested_datetime_utc) {
            params.append("original_parsed_utc", actionableAppointment.parsed_requested_datetime_utc);
        }
      }
      const queryString = params.toString();
      const endpoint = `/appointments/requests/${requestId}/ai-slot-suggestions${queryString ? `?${queryString}` : ""}`;
      
      const response = await apiClient.get(endpoint);
      if (response.data && Array.isArray(response.data.suggestions)) { 
        setAiSuggestedSlots(response.data.suggestions);
      } else {
        console.warn("AI slot suggestions response was not in the expected format:", response.data);
        setAiSuggestedSlots([]); 
      }
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || err.message || "Failed to fetch AI slot suggestions.";
      console.error("Error fetching AI slot suggestions:", errorMsg, err);
      setAiSuggestionsError(errorMsg);
      setAiSuggestedSlots([]); 
    } finally {
      setIsLoadingAiSuggestions(false);
    }
  }, [actionableAppointment]); // Added actionableAppointment to dependencies


  useEffect(() => {
    if (actionableAppointmentId !== null && typeof businessId === 'number' && showNudgeCard) {
      console.log(`Actionable appointment detected (ID: ${actionableAppointmentId}), status: ${actionableAppointment?.status}. Fetching AI slot suggestions for Business ID: ${businessId}.`);
      fetchAiSlotSuggestions(actionableAppointmentId, businessId);
    } else {
      setAiSuggestedSlots([]);
      setAiSuggestionsError(null);
    }
  }, [actionableAppointmentId, businessId, showNudgeCard, fetchAiSlotSuggestions, actionableAppointment?.status]); // Added actionableAppointment?.status

  // Prepare slots for the Nudge Card, prioritizing the customer-confirmed slot if applicable
  const slotsForNudgeCardUI = useMemo(() => {
    let slotToConfirm: AiSuggestedSlot | null = null;
    if (
      actionableAppointment &&
      actionableAppointment.status === AppointmentRequestStatusEnum.CUSTOMER_CONFIRMED_PENDING_OWNER_APPROVAL &&
      actionableAppointment.confirmed_datetime_utc
    ) {
      slotToConfirm = {
        slot_utc: actionableAppointment.confirmed_datetime_utc,
        status_message: "Customer confirmed this time. Click to finalize.",
        isPrimaryConfirmation: true, // Flag this slot
      };
    }

    // Filter out any AI suggested alternative that might be the same as the primary/confirmed one
    const alternativeSlots = aiSuggestedSlots.filter(
      slot => slot.slot_utc !== slotToConfirm?.slot_utc
    );

    if (slotToConfirm) {
      return [slotToConfirm, ...alternativeSlots];
    }
    return alternativeSlots;
  }, [actionableAppointment, aiSuggestedSlots]);


  // --- AI Nudge Assist Card Action Handlers ---
  const commonDraftAndPrepareSend = async (
    intent: AppointmentActionIntentEnum,
    appointment: AppointmentRequest,
    slot?: AiSuggestedSlot 
  ) => {
    if (!businessId || !currentCustomer) {
        console.error("commonDraftAndPrepareSend: Missing businessId or currentCustomer");
        setSendError("Cannot prepare draft: critical business or customer data missing.");
        return;
    }

    setIsProcessingNudgeAction(true);
    setNewMessage(""); 
    setSendError(null);
    setShowNudgeCard(false); 

    const context: AppointmentActionContext = {
      customer_name: currentCustomer.customer_name,
      original_customer_request_text: appointment.original_message_text,
      // For OWNER_ACTION_CONFIRM, use the slot passed, which could be the original confirmed time
      // or a new time if owner is confirming an alternative.
      // For OWNER_ACTION_SUGGEST_RESCHEDULE, owner_proposed_new_time_text will be the new slot.
      parsed_requested_time_text: (intent === AppointmentActionIntentEnum.OWNER_ACTION_CONFIRM && slot && slot.isPrimaryConfirmation) 
                                    ? formatSlotInBusinessTimezone(slot.slot_utc, businessTimezone) 
                                    : appointment.parsed_requested_time_text,
    };
    
    if (slot) { // This slot is the one the owner is acting upon
        context.owner_proposed_new_time_text = formatSlotInBusinessTimezone(slot.slot_utc, businessTimezone);
    }
    
    try {
      const draftPayload: AppointmentActionDraftRequestPayload = { action_type: intent, context };
      const res = await apiClient.post(
        `/appointments/requests/${appointment.id}/draft_action_reply`,
        draftPayload
      );
      setNewMessage(res.data.draft_message); 
      setNudgeCardActionContext({ intent, slot, appointmentId: appointment.id }); 
      inputRef.current?.focus();
    } catch (err: any) {
      const errorDetail = err.response?.data?.detail || `Failed to get AI draft for ${intent}.`;
      console.error(`Error fetching AI draft for ${intent}:`, err);
      setNewMessage(`// AI draft failed: ${errorDetail}\nPlease write your message to ${currentCustomer.customer_name || 'the customer'} manually.`);
      setSendError(errorDetail);
      setNudgeCardActionContext({ intent, slot, appointmentId: appointment.id }); 
      inputRef.current?.focus();
    } finally {
      setIsProcessingNudgeAction(false);
    }
  };

  const handleConfirmAndDraft = useCallback((slot: AiSuggestedSlot) => {
    if (!actionableAppointment) return;
    // Pass the specific slot being confirmed (could be original or a new one from suggestions)
    commonDraftAndPrepareSend(AppointmentActionIntentEnum.OWNER_ACTION_CONFIRM, actionableAppointment, slot);
  }, [actionableAppointment, businessId, currentCustomer, businessTimezone]);

  const handleOfferAlternativeAndDraft = useCallback((slot: AiSuggestedSlot) => {
    if (!actionableAppointment) return;
    commonDraftAndPrepareSend(AppointmentActionIntentEnum.OWNER_ACTION_SUGGEST_RESCHEDULE, actionableAppointment, slot);
  }, [actionableAppointment, businessId, currentCustomer, businessTimezone]);

  const handleDeclineAndDraft = useCallback(() => {
    if (!actionableAppointment) return;
    // For decline, the specific slot isn't as crucial for the draft context as the original request details
    commonDraftAndPrepareSend(AppointmentActionIntentEnum.OWNER_ACTION_DECLINE, actionableAppointment);
  }, [actionableAppointment, businessId, currentCustomer]);

  const handleReplyManuallyOrSuggestOther = useCallback(() => {
    setShowNudgeCard(false); 
    setNudgeCardActionContext(null); 
    setNewMessage(""); 
    inputRef.current?.focus(); 
  }, []);

  const handleSendMessage = async (contentOverride?: string) => {
    const messageToSend = contentOverride || newMessage.trim();
    if (!messageToSend || isSending || !activeCustomerData || !businessId) return;

    if (currentCustomerConsentStatus !== "opted_in") {
      setSendError(`Cannot send: ${activeCustomerData.customer.customer_name || 'Customer'} not opted in. Status: ${currentCustomerConsentStatus.replace(/_/g, ' ').toUpperCase()}`);
      return;
    }

    setIsSending(true); setSendError(null);
    const targetCustomerId = activeCustomerData.customer.id;

    if (nudgeCardActionContext && nudgeCardActionContext.appointmentId) {
      let newStatus: AppointmentRequestStatusEnum | null = null;
      let statusUpdatePayload: Partial<AppointmentRequestStatusUpdateByOwnerPayload> = {
        sms_message_body: messageToSend,
        send_sms_to_customer: true,
        resolution_notes: `Owner action via AI Nudge Assist: ${nudgeCardActionContext.intent}`,
      };

      switch (nudgeCardActionContext.intent) {
        case AppointmentActionIntentEnum.OWNER_ACTION_CONFIRM:
          newStatus = AppointmentRequestStatusEnum.CONFIRMED_BY_OWNER;
          if (nudgeCardActionContext.slot) { // This slot is the one being confirmed
            statusUpdatePayload.owner_suggested_datetime_utc_iso = nudgeCardActionContext.slot.slot_utc; 
            statusUpdatePayload.owner_suggested_time_text = formatSlotInBusinessTimezone(nudgeCardActionContext.slot.slot_utc, businessTimezone);
          } else if (actionableAppointment?.confirmed_datetime_utc && actionableAppointment.status === AppointmentRequestStatusEnum.CUSTOMER_CONFIRMED_PENDING_OWNER_APPROVAL) {
            // Fallback if somehow slot is not in context but it's a primary confirmation
            statusUpdatePayload.owner_suggested_datetime_utc_iso = actionableAppointment.confirmed_datetime_utc;
            statusUpdatePayload.owner_suggested_time_text = formatSlotInBusinessTimezone(actionableAppointment.confirmed_datetime_utc, businessTimezone);
          } else if (actionableAppointment?.parsed_requested_datetime_utc) { // General fallback if no specific slot
            statusUpdatePayload.owner_suggested_datetime_utc_iso = actionableAppointment.parsed_requested_datetime_utc;
            statusUpdatePayload.owner_suggested_time_text = actionableAppointment.parsed_requested_time_text || formatSlotInBusinessTimezone(actionableAppointment.parsed_requested_datetime_utc, businessTimezone);
          }
          break;
        case AppointmentActionIntentEnum.OWNER_ACTION_SUGGEST_RESCHEDULE:
          newStatus = AppointmentRequestStatusEnum.OWNER_PROPOSED_RESCHEDULE;
           if (nudgeCardActionContext.slot) {
            statusUpdatePayload.owner_suggested_datetime_utc_iso = nudgeCardActionContext.slot.slot_utc;
            statusUpdatePayload.owner_suggested_time_text = formatSlotInBusinessTimezone(nudgeCardActionContext.slot.slot_utc, businessTimezone);
          }
          break;
        case AppointmentActionIntentEnum.OWNER_ACTION_DECLINE:
          newStatus = AppointmentRequestStatusEnum.DECLINED_BY_OWNER;
          break;
      }

      if (newStatus) {
        statusUpdatePayload.new_status = newStatus;
        try {
          await apiClient.patch(
            `/appointments/requests/${nudgeCardActionContext.appointmentId}/status`,
            statusUpdatePayload
          );
        } catch (err: any) {
          console.error("Failed to update appointment status:", err);
          setSendError(`Message may have sent, but failed to update appointment status: ${err.response?.data?.detail || err.message}`);
        }
      } else {
         console.warn("Message sent via nudge context, but no new status determined. This is unexpected.", nudgeCardActionContext);
         try {
            await apiClient.post(`/conversations/customer/${targetCustomerId}/reply`, { message: messageToSend });
         } catch (err: any) {
            setSendError(`Failed to send message after nudge action (status determination issue): ${err.response?.data?.detail || err.message}`);
            setIsSending(false);
            return;
         }
      }
    } else {
        try {
            await apiClient.post(`/conversations/customer/${targetCustomerId}/reply`, { message: messageToSend });
        } catch (err:any) {
            setSendError(`Failed to send: ${err.response?.data?.detail || err.message}`);
            setIsSending(false);
            return;
        }
    }

    setNewMessage("");
    setSelectedAiDraftIdForEdit(null);
    setEditingAiDraftOriginalContent(null);
    setNudgeCardActionContext(null); 
    setShowNudgeCard(true); 
    
    if (activeCustomerId && businessId) {
      fetchActiveCustomerData(activeCustomerId, businessId); 
    }
    if (businessId) {
      fetchCustomerSummaries(businessId, filterOption, false); 
    }
    setIsSending(false);
  };

  const handleEditAiDraft = (draft: TimelineEntry) => {
    if (draft.is_ai_draft_for_review) {
      setNudgeCardActionContext(null); 
      setShowNudgeCard(true); 
      setSelectedAiDraftIdForEdit(draft.id); setNewMessage(draft.content);
      setEditingAiDraftOriginalContent(draft.raw_content || draft.content);
      inputRef.current?.focus();
    }
  };

  const handleCancelEditAiDraft = () => {
    setNewMessage(""); setSelectedAiDraftIdForEdit(null); setEditingAiDraftOriginalContent(null);
  };

  const handleDeleteAiDraft = async (draftId: string | number) => { 
    const engagementIdStr = typeof draftId === 'string' && draftId.startsWith('eng-ai-') ? draftId.substring(7) : String(draftId);
    const engagementId = parseInt(engagementIdStr, 10);
    if (isNaN(engagementId)) { 
      alert("Could not identify draft for deletion."); return; 
    }
    if (window.confirm("Delete this AI draft?")) {
      try {
        await apiClient.delete(`/engagements/${engagementId}`);
        if (selectedAiDraftIdForEdit === draftId) handleCancelEditAiDraft();
        if (activeCustomerId && businessId) fetchActiveCustomerData(activeCustomerId, businessId);
      } catch (err: any) { 
        alert(`Failed to delete draft: ${err.response?.data?.detail || err.message}`); 
      }
    }
   };

  const handleOpenEditScheduledModal = (entry: TimelineEntry) => { 
    setEditingScheduledMessage(entry); 
    setEditedScheduledContent(entry.content);
    setEditedScheduledTimeISO(entry.timestamp ? formatForDateTimeLocal(entry.timestamp) : "");
    setShowEditScheduledModal(true); 
    setSendError(null);
  };
  const handleSaveScheduledEdit = async () => { 
    if (!editingScheduledMessage || !editedScheduledContent.trim() || !editedScheduledTimeISO) {
      setSendError("Content and time required for scheduled message edit."); return;
    }
    setIsUpdatingScheduled(true); setSendError(null);
    try {
        const localTime = parseISO(editedScheduledTimeISO); 
        const scheduledTimeUtc = formatISO(localTime); 
        const updatePayload: MessageUpdatePayload = {
            content: editedScheduledContent, 
            scheduled_send_at: scheduledTimeUtc,
        };
        await apiClient.put(`/messages/${String(editingScheduledMessage.id)}`, updatePayload);
        setShowEditScheduledModal(false);
        if (activeCustomerId && businessId) fetchActiveCustomerData(activeCustomerId, businessId);
    } catch (err: any) { 
        setSendError(`Failed to update scheduled message: ${err.response?.data?.detail || err.message}`);
    } finally { 
        setIsUpdatingScheduled(false); 
    }
  };
  const handleCancelScheduledMessage = async (messageId: string | number) => { 
    if (window.confirm("Are you sure you want to cancel this scheduled message?")) {
      setIsUpdatingScheduled(true); 
      try {
        await apiClient.delete(`/messages/${String(messageId)}`); 
        if (activeCustomerId && businessId) fetchActiveCustomerData(activeCustomerId, businessId); 
      } catch (err: any) { 
        alert(`Failed to cancel scheduled message: ${err.response?.data?.detail || err.message}`);
      } finally { 
        setIsUpdatingScheduled(false); 
      }
    }
  };
  const getAppointmentTimeText = (apt: AppointmentRequest | null | undefined): string => {
    if (!apt) return "Not specified";
    if (apt.status === AppointmentRequestStatusEnum.OWNER_PROPOSED_RESCHEDULE && apt.owner_suggested_time_text) {
        return apt.owner_suggested_time_text;
    }
    if (apt.status === AppointmentRequestStatusEnum.CONFIRMED_BY_OWNER && apt.confirmed_datetime_utc) {
        return formatSlotInBusinessTimezone(apt.confirmed_datetime_utc, businessTimezone) + " (Confirmed)";
    }
     // For CUSTOMER_CONFIRMED_PENDING_OWNER_APPROVAL, display the confirmed_datetime_utc if available
    if (apt.status === AppointmentRequestStatusEnum.CUSTOMER_CONFIRMED_PENDING_OWNER_APPROVAL && apt.confirmed_datetime_utc) {
      return formatSlotInBusinessTimezone(apt.confirmed_datetime_utc, businessTimezone) + " (Pending Your Approval)";
    }
    return apt.parsed_requested_time_text || (apt.parsed_requested_datetime_utc ? formatSlotInBusinessTimezone(apt.parsed_requested_datetime_utc, businessTimezone) : "Time not set");
  };

  if (!businessId && isLoadingConversations) {
    return <div className="h-screen flex items-center justify-center bg-[#0B0E1C] text-white text-lg"><RefreshCw className="w-6 h-6 mr-2 animate-spin" />Loading Business...</div>;
  }
  if (!businessId && fetchError) {
    return <div className="h-screen flex flex-col items-center justify-center bg-[#0B0E1C] text-red-400 p-4 text-center">
      <AlertTriangle className="w-12 h-12 mb-3 text-red-500" /><p className="text-xl font-semibold">Error Loading Business</p><p className="text-sm mt-1">{fetchError}</p>
    </div>;
  }

  const isInputDisabled = isSending || !currentCustomer || currentCustomerConsentStatus !== "opted_in" || isProcessingNudgeAction;

  return (
    <div className="h-screen flex md:flex-row flex-col bg-[#0B0E1C] text-gray-200 overflow-hidden">
      <aside className={clsx(
        "w-full md:w-80 lg:w-96 bg-[#1A1D2D] border-r border-[#2A2F45]",
        "fixed md:static inset-0 z-30 md:z-auto",
        "transition-transform duration-300 ease-in-out",
        showMobileDrawer ? "translate-x-0" : "-translate-x-full md:translate-x-0",
        "flex flex-col h-full"
      )}>
        <div className="flex justify-between items-center p-4 border-b border-[#2A2F45] shrink-0">
          <h2 className="text-2xl font-bold text-white">Inbox</h2>
           {showMobileDrawer && (
            <button onClick={() => setShowMobileDrawer(false)} className="p-2 md:hidden hover:bg-[#242842] rounded-lg text-gray-300" aria-label="Close contact list"><XCircle size={20}/></button>
          )}
        </div>
        <div className="p-4 border-b border-[#2A2F45] shrink-0">
          <label htmlFor="filter" className="text-sm text-gray-400 mr-2 sr-only">Filter:</label>
          <div className="relative inline-block w-full">
            <select
              id="filter"
              value={filterOption}
              onChange={(e) => setFilterOption(e.target.value as FilterOption)}
              className="w-full p-2.5 bg-[#2A2F45] border border-[#3B3F58] rounded-lg text-white focus:ring-1 focus:ring-blue-500 appearance-none pr-8 text-sm"
            >
              <option value="all">All Conversations</option>
              <option value="needs_action_appointments">🚦 Needs Action (Appointments)</option>
              <option value="upcoming_appointments">🗓️ Upcoming Appointments</option>
              <option value="no_appointment_history">🗂️ No Appointment History</option>
            </select>
            <FilterIcon className="absolute left-2.5 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
            <ChevronDown className="absolute right-2.5 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400 pointer-events-none" />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">
          {isLoadingConversations && customerSummaries.length === 0 &&
            <div className="p-4 text-gray-400 text-center flex items-center justify-center"><RefreshCw className="w-4 h-4 mr-2 animate-spin"/>Loading conversations...</div>
          }
          {!isLoadingConversations && customerSummaries.length === 0 && (
            <p className="p-4 text-gray-400 text-center">No conversations {filterOption !== 'all' ? 'match your filter' : 'yet'}.</p>
          )}
          {customerSummaries.map((cs) => {
            const isActionable = cs.latest_appointment_request_status === AppointmentRequestStatusEnum.PENDING_OWNER_ACTION ||
                                 cs.latest_appointment_request_status === AppointmentRequestStatusEnum.CUSTOMER_REQUESTED_RESCHEDULE ||
                                 cs.latest_appointment_request_status === AppointmentRequestStatusEnum.CUSTOMER_CONFIRMED_PENDING_OWNER_APPROVAL;
            const isUpcomingConfirmed = cs.latest_appointment_request_status === AppointmentRequestStatusEnum.CONFIRMED_BY_OWNER &&
                                       cs.latest_appointment_request_datetime_utc &&
                                       isFuture(parseISO(cs.latest_appointment_request_datetime_utc));
            let subText = cs.last_message_content || "No recent messages";
            if (isActionable) {
                subText = `🚦 Appt. Request: ${cs.latest_appointment_request_time_text || (cs.latest_appointment_request_datetime_utc ? formatSlotInBusinessTimezone(cs.latest_appointment_request_datetime_utc, businessTimezone) : "Time not set")}`;
            } else if (isUpcomingConfirmed && cs.latest_appointment_request_datetime_utc) {
                subText = `✅ Confirmed: ${cs.latest_appointment_request_time_text || formatSlotInBusinessTimezone(cs.latest_appointment_request_datetime_utc, businessTimezone)}`;
            }
            return (
              <button
                key={cs.customer_id}
                onClick={() => { setActiveCustomerId(cs.customer_id); setShowMobileDrawer(false);}}
                className={clsx(
                  "w-full text-left p-3 hover:bg-[#242842] transition-colors border-b border-[#2A2F45] focus:outline-none focus:ring-2 focus:ring-blue-500",
                  activeCustomerId === cs.customer_id ? "bg-[#2A2F45]" : "bg-transparent",
                )}
              >
                <div className="flex justify-between items-center">
                  <h3 className={clsx("text-sm truncate font-medium", isActionable ? "text-yellow-400" : "text-white")}>
                    {isActionable && <TrafficCone className="inline w-4 h-4 mr-1.5 mb-0.5" />}
                    {cs.customer_name}
                  </h3>
                  {cs.last_message_timestamp && (
                    <span className="text-xs whitespace-nowrap ml-2 text-gray-400">
                      {formatDateShort(cs.last_message_timestamp)}
                    </span>
                  )}
                </div>
                <p className="text-xs truncate mt-1 text-gray-400">{subText}</p>
              </button>
            );
            })}
        </div>
      </aside>

      <main className="flex-1 flex flex-col bg-[#0F1221] h-full md:min-h-0">
        <div className="md:hidden flex items-center justify-between p-4 bg-[#1A1D2D] border-b border-[#2A2F45] shrink-0">
            <h1 className="text-lg font-semibold text-white truncate max-w-[calc(100%-4rem)]">
                {currentCustomer ? currentCustomer.customer_name : "Select Conversation"}
            </h1>
            <button
            onClick={() => setShowMobileDrawer(true)} 
            className="p-2 hover:bg-[#242842] rounded-lg transition-colors"
            aria-label="Open contact list"
            >
            <SidebarOpen className="w-5 h-5 text-white" />
            </button>
        </div>

        {isLoadingChat && (
             <div className="flex-1 flex flex-col items-center justify-center text-gray-400 p-4">
                <RefreshCw className="w-8 h-8 mb-4 text-gray-500 animate-spin" />
                <p className="text-lg">Loading conversation...</p>
             </div>
        )}

        {!isLoadingChat && fetchError && activeCustomerId && !activeCustomerData && (
             <div className="flex-1 flex flex-col items-center justify-center text-red-400 p-4 text-center">
                <AlertTriangle className="w-12 h-12 mb-3 text-red-500" />
                <p className="text-xl font-semibold">Error Loading Chat</p>
                <p className="text-sm mt-1">{fetchError.includes(String(activeCustomerId)) ? fetchError : "Could not load this conversation."}</p>
             </div>
        )}

        {activeCustomerData && currentCustomer ? (
          <>
            <div className="p-3.5 bg-[#1A1D2D] border-b border-[#2A2F45] shrink-0">
              <h3 className="text-lg font-semibold text-white">{currentCustomer.customer_name || "Customer"}</h3>
              <p className="text-xs text-gray-400 flex items-center">
                <Phone size={12} className="mr-1.5 inline"/> {currentCustomer.phone} &bull;
                <span className={clsx("ml-1.5 px-1.5 py-0.5 rounded text-xs font-medium",
                  currentCustomerConsentStatus === 'opted_in' ? "bg-green-700 text-green-100" :
                  currentCustomerConsentStatus === 'opted_out' ? "bg-red-700 text-red-100" :
                  currentCustomerConsentStatus === 'pending' ? "bg-yellow-700 text-yellow-100" :
                  currentCustomerConsentStatus === 'waiting' ? "bg-gray-600 text-gray-200" :
                                                              "bg-orange-700 text-orange-100" 
                )}>
                  {currentCustomerConsentStatus === 'opted_in' && "OPTED IN"}
                  {currentCustomerConsentStatus === 'opted_out' && "OPTED OUT"}
                  {currentCustomerConsentStatus === 'pending' && "PENDING CONSENT"}
                  {currentCustomerConsentStatus === 'waiting' && "AWAITING RESPONSE"}
                  {currentCustomerConsentStatus === 'error' && "STATUS ERROR"}
                </span>
                {currentCustomer.latest_consent_updated &&
                  <span className="ml-2 text-gray-500 text-xs">(as of {formatDateShort(currentCustomer.latest_consent_updated)})</span>
                }
              </p>
            </div>

            {actionableAppointment && businessId && showNudgeCard && !isProcessingNudgeAction && (
              <AppointmentNudgeAssistCard
                actionableAppointment={actionableAppointment}
                aiSuggestedSlots={slotsForNudgeCardUI} 
                isLoadingSuggestions={isLoadingAiSuggestions}
                suggestionsError={aiSuggestionsError}
                currentCustomerName={currentCustomer?.customer_name}
                businessTimezone={businessTimezone}
                onConfirmAndDraft={handleConfirmAndDraft}
                onOfferAlternativeAndDraft={handleOfferAlternativeAndDraft}
                onDeclineAndDraft={handleDeclineAndDraft}
                onReplyManuallyOrSuggestOther={handleReplyManuallyOrSuggestOther}
                onRetryFetchSuggestions={() => {
                  if (actionableAppointment?.id && businessId) {
                    fetchAiSlotSuggestions(actionableAppointment.id, businessId);
                  }
                }}
              />
            )}
            
            {isProcessingNudgeAction && (
                <div className="p-4 text-center text-slate-400 bg-slate-800 border-b border-slate-700">
                    <RefreshCw className="w-5 h-5 animate-spin inline mr-2" /> Processing AI Assist action...
                </div>
            )}

            <div ref={chatContainerRef} className="flex flex-col flex-1 overflow-y-auto p-4 space-y-3 bg-[#0B0E1C]">
              {timelineEntries.map((entry) => (
                <div
                  key={entry.id}
                  data-message-id={entry.id}
                  className={clsx(
                    "p-3 rounded-xl max-w-[80%] break-words text-sm shadow-md flex flex-col",
                    entry.type === "customer" ? "self-start bg-[#2A2F45] text-white mr-auto" : "self-end bg-blue-600 text-white ml-auto",
                    entry.type === "appointment_related" && "!bg-indigo-600", 
                    entry.type === "outbound_ai_reply" && "!bg-teal-600", 
                    entry.is_ai_draft_for_review && "!bg-yellow-600 !bg-opacity-20 !text-yellow-200 !border !border-yellow-500",
                    entry.is_pending_scheduled && "!bg-gray-700 !bg-opacity-60 !text-gray-300 !border !border-gray-600",
                    entry.type === "system_notification" && "!bg-purple-700 !bg-opacity-50 !text-purple-200"
                  )}
                >
                  {entry.sender_name && entry.type !== "customer" && <p className="text-xs font-semibold mb-1 opacity-80 self-start">{entry.sender_name}</p>}
                  {entry.is_faq_autopilot && <p className="text-xs text-blue-300 mb-1 italic self-start">(Auto-reply: FAQ)</p>}
                  {entry.is_ai_initial_reply && <p className="text-xs text-teal-300 mb-1 italic self-start">(AI Initial Reply)</p>}
                  {entry.is_ai_draft_for_review && <p className="text-xs text-yellow-300 mb-1 italic self-start flex items-center"><ClipboardEdit size={14} className="mr-1"/> AI Draft for Review</p>}
                  {entry.is_pending_scheduled && <p className="text-xs text-gray-400 mb-1 italic self-start flex items-center"><Clock size={14} className="mr-1"/> {entry.scheduled_message_type?.toUpperCase()} Scheduled: {formatMessageTimestamp(entry.timestamp)}</p>}
                  {entry.appointment_lifecycle_tag && <p className="text-xs opacity-90 mb-1 italic self-start flex items-center">{entry.appointment_lifecycle_tag}</p>}

                  <p className="whitespace-pre-wrap">{entry.content}</p>

                  <div className="flex items-center self-end mt-1.5 opacity-80 text-xs">
                    {entry.timestamp && <span>{formatMessageTimestamp(entry.timestamp)}</span>}
                    {entry.type !== "customer" && entry.status === 'delivered' && <CheckCheck size={14} className="ml-1.5 text-green-400" />}
                    {entry.type !== "customer" && (entry.status === 'sent' || entry.status === 'accepted') && <Check size={14} className="ml-1.5 text-gray-300" />}
                    {entry.type !== "customer" && (entry.status === 'queued' || entry.status === 'pending_send') && <Clock size={12} className="ml-1.5 text-gray-400" />}
                    {entry.status === 'failed' && <AlertCircle size={12} className="ml-1.5 text-red-400" />}
                  </div>

                  {entry.is_ai_draft_for_review && (
                    <div className="flex gap-2 mt-2.5 self-end border-t border-yellow-500 border-opacity-30 pt-2">
                      <button onClick={() => handleEditAiDraft(entry)} className="px-2.5 py-1 bg-gray-600 hover:bg-gray-500 rounded text-white text-xs flex items-center"><Edit3 size={12} className="mr-1"/> Edit</button>
                      <button onClick={() => handleSendMessage(entry.raw_content || entry.content)} disabled={isSending || isInputDisabled} className="px-2.5 py-1 bg-yellow-500 hover:bg-yellow-600 rounded text-black text-xs font-semibold flex items-center"><SendHorizonal size={12} className="mr-1"/> Send Now</button>
                      <button onClick={() => handleDeleteAiDraft(entry.id)} className="p-1.5 bg-red-700 hover:bg-red-600 rounded text-white text-xs flex items-center"><Trash2 size={12}/></button>
                    </div>
                  )}
                  {entry.is_pending_scheduled && (
                    <div className="flex gap-2 mt-2.5 self-end border-t border-gray-600 border-opacity-50 pt-2">
                      <button onClick={() => handleOpenEditScheduledModal(entry)} className="px-2.5 py-1 bg-gray-500 hover:bg-gray-400 rounded text-white text-xs flex items-center"><Settings2 size={12} className="mr-1"/> Edit</button>
                      <button onClick={() => handleCancelScheduledMessage(String(entry.id))} className="px-2.5 py-1 bg-red-700 hover:bg-red-600 rounded text-white text-xs flex items-center"><XCircle size={12} className="mr-1"/> Cancel</button>
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div className="p-4 bg-[#1A1D2D] border-t border-[#2A2F45] shrink-0">
              {sendError && <p className="text-xs text-red-400 mb-2">{sendError}</p>}
              <div className="flex items-center gap-2">
                <input
                  ref={inputRef}
                  type="text"
                  value={newMessage}
                  onChange={(e) => {
                    setNewMessage(e.target.value);
                  }}
                  onKeyPress={(e) => e.key === "Enter" && !isSending && handleSendMessage()}
                  placeholder={nudgeCardActionContext ? "Review AI draft or edit..." : (selectedAiDraftIdForEdit ? "Editing AI Draft..." : "Type a message...")}
                  className="flex-1 p-2.5 bg-[#2A2F45] border border-[#3B3F58] rounded-lg text-white placeholder-gray-400 focus:ring-1 focus:ring-blue-500 focus:border-blue-500 outline-none"
                  disabled={isInputDisabled}
                />
                <button
                  onClick={() => handleSendMessage()}
                  disabled={isInputDisabled || !newMessage.trim()}
                  className="p-2.5 bg-blue-600 hover:bg-blue-700 rounded-lg text-white disabled:opacity-50 transition-colors flex items-center justify-center aspect-square"
                  aria-label="Send message"
                >
                  {isSending ? <RefreshCw className="w-5 h-5 animate-spin" /> : <SendHorizonal className="w-5 h-5" />}
                </button>
              </div>
              {(selectedAiDraftIdForEdit || nudgeCardActionContext) && ( 
                <Button 
                    variant="ghost" 
                    size="sm"
                    onClick={() => {
                        setNewMessage("");
                        setSelectedAiDraftIdForEdit(null);
                        setEditingAiDraftOriginalContent(null);
                        setNudgeCardActionContext(null);
                        setShowNudgeCard(true); 
                    }} 
                    className="text-xs text-gray-400 hover:text-gray-200 mt-1.5 pl-0"
                >
                    Cancel AI Draft / Action
                </Button>
              )}
              {currentCustomer && currentCustomerConsentStatus !== "opted_in" && (
                <p className="text-xs text-red-400 mt-1.5">Cannot send messages: Customer not opted-in ({currentCustomerConsentStatus.replace(/_/g, ' ').toUpperCase()}).</p>
              )}
            </div>
          </>
        ) : (
         !isLoadingChat && !isLoadingConversations &&
          <div className="flex-1 flex flex-col items-center justify-center text-gray-400 p-4 text-center">
            <MessageCircleIcon className="w-16 h-16 mb-4 text-gray-500" />
            <p className="text-lg">Select a conversation</p>
            <p className="text-sm">Choose a customer from the list to view messages.</p>
            {customerSummaries.length === 0 && !isLoadingConversations && !fetchError && (
              <p className="text-sm mt-2">No conversations to display for the current filter.</p>
            )}
          </div>
        )}
      </main>

      {showEditScheduledModal && editingScheduledMessage && (
         <div className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50 p-4">
          <div className="bg-[#1A1D2D] p-6 rounded-lg shadow-xl w-full max-w-md text-white border border-[#2A2F45]">
            <h4 className="text-lg font-semibold mb-4">Edit Scheduled Message</h4>
            <p className="text-sm text-gray-400 mb-1">Type: <span className="font-medium text-gray-200">{editingScheduledMessage.scheduled_message_type?.toUpperCase() || "Message"}</span></p>
            <p className="text-xs text-gray-500 mb-3">Original Time: {formatMessageTimestamp(editingScheduledMessage.timestamp)}</p>
            
            <div className="mb-4">
                <label htmlFor="editScheduledTimeISO" className="block text-sm font-medium text-gray-300 mb-1">New Scheduled Date & Time (Local):</label>
                <input type="datetime-local" id="editScheduledTimeISO" value={editedScheduledTimeISO} onChange={e => setEditedScheduledTimeISO(e.target.value)} className="w-full p-2 bg-[#2A2F45] border border-[#3B3F58] rounded-lg text-white"/>
            </div>
            <div className="mb-4">
                <label htmlFor="editScheduledContent" className="block text-sm font-medium text-gray-300 mb-1">Message Content:</label>
                <textarea id="editScheduledContent" rows={3} value={editedScheduledContent} onChange={e => setEditedScheduledContent(e.target.value)} className="w-full p-2 bg-[#2A2F45] border border-[#3B3F58] rounded-lg text-white"></textarea>
            </div>
            {sendError && <p className="text-xs text-red-400 mb-3">{sendError}</p>}
             <div className="flex justify-end gap-3 mt-5">
                <button onClick={() => setShowEditScheduledModal(false)} className="px-4 py-2 text-sm bg-gray-600 hover:bg-gray-700 rounded-md" disabled={isUpdatingScheduled}>Cancel</button>
                <button onClick={handleSaveScheduledEdit} className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 rounded-md disabled:opacity-50" disabled={isUpdatingScheduled || !editedScheduledContent.trim() || !editedScheduledTimeISO}>
                    {isUpdatingScheduled ? <RefreshCw className="w-4 h-4 mr-2 animate-spin"/> : null}
                    Save Changes
                </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}