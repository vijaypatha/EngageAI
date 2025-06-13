// frontend/src/types/index.ts

// Define the Tag type
export interface Tag {
    id: number;
    name: string;
  }
  
  // Basic Customer Info for nested objects
  export interface CustomerBasicInfo {
    id: number;
    name: string;
  }
  
  // Represents the raw message object from the API.
  export interface BackendMessage {
      id: string | number;
      type: "inbound" | "outbound" | "scheduled" | "scheduled_pending" | "failed_to_send" | "unknown_business_message" | "outbound_ai_reply";
      content: any;
      status?: string;
      scheduled_time?: string | null;
      sent_time?: string | null;
      customer_id: number;
      ai_response?: string; // The content of a pending AI draft, attached to an inbound message
      ai_draft_id?: number; // The ID of the engagement for draft actions
      contextual_action?: { // NEW: Add contextual action info
          type: string; // e.g., "REQUEST_REVIEW"
          nudge_id: number; // The ID of the related nudge
          ai_suggestion?: string; // AI's suggestion for this action
      };
  }
  
  // Represents the raw customer object from the `/review/full-customer-history` endpoint
  // (Note: This type will now primarily be used for the active conversation's detailed history)
  export interface RawCustomerSummary {
      customer_id: number;
      customer_name: string;
      phone: string;
      opted_in: boolean;
      consent_status: string;
      consent_updated?: string | null;
      message_count: number; // Total messages in this customer's history
      messages: BackendMessage[]; // All messages for this specific customer
  }
  
  // Represents a processed customer summary for display in the sidebar (from /review/inbox/summaries)
  export interface InboxCustomerSummary {
      customer_id: number;
      customer_name: string;
      phone: string;
      opted_in: boolean; // From latest consent log
      consent_status: string; // From latest consent log
      last_message_content: string | null; // Snippet of last message
      last_message_timestamp: string | null; // Timestamp of last message
      unread_message_count: number; // NEW: Number of unread messages (calculated by backend)
      business_id: number;
      // is_unread will now be derived from unread_message_count > 0 on the frontend if needed for styling
  }
  
  // Represents the paginated response structure from /review/inbox/summaries
  export interface PaginatedInboxSummariesResponse {
      items: InboxCustomerSummary[];
      total: number;
      page: number;
      size: number;
      pages: number;
  }
  
  // Represents a processed message object for display in the timeline.
  export interface TimelineEntry {
      id: string | number;
      type: "inbound" | "outbound" | "scheduled" | "scheduled_pending" | "failed_to_send" | "unknown_business_message" | "outbound_ai_reply";
      content: string;
      timestamp: string | null;
      customer_id: number;
      status?: string;
      is_faq_answer?: boolean;
      appended_opt_in_prompt?: boolean;
      ai_response?: string; // The content of a pending AI draft
      ai_draft_id?: number; // The ID for draft actions
      contextual_action?: { // NEW: Add contextual action info to TimelineEntry
          type: string; // e.g., "REQUEST_REVIEW"
          nudge_id: number; // The ID of the related nudge
          ai_suggestion?: string; // AI's suggestion for this action
      };
  }
  
  // NEW: Define and export the Customer interface as it's used by other frontend pages.
  // This should mirror the structure returned by your backend's Customer schema (excluding relationships).
  export interface Customer {
    id: number;
    customer_name: string;
    phone: string;
    lifecycle_stage: string;
    pain_points?: string | null;
    interaction_history?: string | null;
    business_id: number;
    timezone?: string | null;
    opted_in?: boolean;
    sms_opt_in_status: string;
    is_generating_roadmap?: boolean;
    last_generation_attempt?: string | null; // Assuming datetime is string (ISO)
    created_at: string;
    updated_at?: string | null;
    latest_consent_status?: string | null;
    latest_consent_updated?: string | null;
    tags?: Tag[]; // Assuming Tag is defined
    last_read_at?: string | null; // Add if used by frontend directly
  }
  
  // UPDATED: Define and export the AutopilotMessage interface for the AutopilotPlanView.
  // Now includes 'content' and a nested 'customer' object.
  export interface AutopilotMessage {
    id: number;
    content: string; // The message text (aligned with backend output)
    status: string; // e.g., "draft", "scheduled", "sent"
    scheduled_time: string; // The exact date and time the message will be sent (ISO format string)
    customer: CustomerBasicInfo; // Nested customer object with id and name
    // smsContent, smsTiming, send_datetime_utc, relevance, success_indicator, no_response_plan are removed
    // or made optional if not strictly used by the component in its current rendering.
    // We'll primarily rely on 'content' and 'scheduled_time' for the UI display.
  }