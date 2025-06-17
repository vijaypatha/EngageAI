// frontend/src/types/index.ts

// Define the Tag type
export interface Tag {
  id: number;
  name: string;
}

// Basic Customer Info for nested objects
export interface CustomerBasicInfo {
id: number;
customer_name: string;
}

// --- START: Types for Autopilot Instant Replies ---

export interface CustomFaqItem {
question: string;
answer: string;
}

export interface StructuredFaqData {
operating_hours?: string;
address?: string;
website?: string;
custom_faqs?: CustomFaqItem[];
}

export interface BusinessProfile {
id: number;
enable_ai_faq_auto_reply: boolean;
structured_faq_data?: StructuredFaqData;
timezone?: string;
}

// --- END: Types for Autopilot Instant Replies ---

// Represents the raw message object from the API.
export interface BackendMessage {
  id: string | number;
  type: "inbound" | "outbound" | "scheduled" | "scheduled_pending" | "failed_to_send" | "unknown_business_message" | "outbound_ai_reply";
  content: any;
  status?: string;
  scheduled_time?: string | null;
  sent_time?: string | null;
  customer_id: number;
  ai_response?: string;
  ai_draft_id?: number;
  contextual_action?: { 
      type: string;
      nudge_id: number;
      ai_suggestion?: string;
  };
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
export interface InboxCustomerSummary {
  customer_id: number;
  customer_name: string;
  phone: string;
  opted_in: boolean;
  consent_status: string;
  last_message_content: string | null;
  last_message_timestamp: string | null;
  unread_message_count: number;
  business_id: number;
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
  customer_name?: string;
  status?: string;
  is_faq_answer?: boolean;
  appended_opt_in_prompt?: boolean;
  ai_response?: string;
  ai_draft_id?: number;
  contextual_action?: {
      type: string;
      nudge_id: number;
      ai_suggestion?: string;
  };
}

// Represents the full Customer object
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
last_generation_attempt?: string | null;
created_at: string;
updated_at?: string | null;
latest_consent_status?: string | null;
latest_consent_updated?: string | null;
tags?: Tag[];
last_read_at?: string | null;
}

// Represents a scheduled message for the AutopilotPlanView.
export interface AutopilotMessage {
id: number;
content: string;
status: string;
scheduled_time: string;
customer: CustomerBasicInfo;
}

// --- NEW INTERFACE FOR APPROVAL QUEUE ---
export interface ApprovalQueueItem {
id: number;
content: string;
status: 'pending_approval'; // Type-safe status
created_at: string; // ISO 8601 string
customer: CustomerBasicInfo;
message_metadata?: {
  source?: string;
  campaign_type?: string;
  nudge_id?: number;
  reason_to_believe?: string;
};
}
