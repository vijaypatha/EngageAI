// FILE: frontend/src/types/index.ts

// Define the Tag type
export interface Tag {
  id: number;
  name: string;
}

// Define the Customer structure
export interface Customer {
  id: number;
  customer_name: string;
  phone: string;
  lifecycle_stage: string;
  pain_points: string;
  interaction_history: string;
  business_id: number;
  timezone?: string | null;
  opted_in?: boolean | null;
  is_generating_roadmap?: boolean | null;
  last_generation_attempt?: string | null;
  created_at: string;
  updated_at?: string | null;
  latest_consent_status?: string | null;
  latest_consent_updated?: string | null;
  tags?: Tag[] | null;
}

// Defines the summary data for a customer, used in lists.
export interface CustomerSummarySchema {
  id: number;
  customer_name: string;
  phone?: string | null;
  lifecycle_stage?: string | null;
  opted_in: boolean;
  latest_consent_status?: string | null;
  latest_consent_updated?: string | null;
  tags: Tag[];
  business_id: number;
}

// NEW: Defines the shape of a scheduled message for the Autopilot Plan view.
export interface AutopilotMessage {
  id: number;
  content: string;
  status: string;
  scheduled_time: string; // ISO string
  customer: {
    id: number;
    name: string;
  };
}

// Represents the raw message object from the API.
export interface BackendMessage {
  id: string | number;
  type: "inbound" | "outbound" | "scheduled" | "scheduled_pending" | "failed_to_send" | "unknown_business_message" | "outbound_ai_reply";
  content: any;
  status?: string;
  scheduled_time?: string | null;
  sent_time?: string | null;
  source?: string;
  customer_id: number;
  is_hidden?: boolean;
  response?: string;
  ai_response?: string;
  ai_draft_id?: number;
}

// Represents the raw customer object from the `/review/full-customer-history` endpoint
export interface RawCustomerSummary {
  customer_id: number;
  customer_name: string;
  phone: string;
  opted_in: boolean;
  consent_status: string;
  consent_updated?: string | null;
  message_count: number;
  messages: BackendMessage[];
}

// Represents a processed customer summary for display in the sidebar
export interface InboxCustomerSummary extends RawCustomerSummary {
  last_message_preview: string;
  last_message_timestamp: string;
  is_unread: boolean;
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
  ai_response?: string;
  ai_draft_id?: number;
}