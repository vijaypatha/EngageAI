// frontend/src/lib/api.ts
import axios from 'axios';
import useSWR from 'swr';
// --- Corrected Import ---
import { Customer, Tag } from '../types'; // Import BOTH Customer and Tag from your types file


// --- SWR Fetcher ---
const fetcher = (url: string) => apiClient.get(url).then(res => res.data);

// --- Existing apiClient setup ---
export const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000',
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

// === Tag API Functions ===
// These function signatures now correctly use the imported Tag type

export const getBusinessTags = async (businessId: number): Promise<Tag[]> => {
  const response = await apiClient.get<Tag[]>(`/tags/business/${businessId}/tags`);
  return response.data;
};
export const useBusinessTags = (businessId: number | null) => useSWR<Tag[]>(businessId ? `/tags/business/${businessId}/tags` : null, fetcher);

export const createBusinessTag = async (businessId: number, tagName: string): Promise<Tag> => {
  const response = await apiClient.post<Tag>(`/tags/business/${businessId}/tags`, { name: tagName });
  return response.data;
};

export const deleteTagPermanently = async (tagId: number): Promise<void> => {
  await apiClient.delete(`/tags/tags/${tagId}`);
};

export const setCustomerTags = async (customerId: number, tagIds: number[]): Promise<void> => {
  await apiClient.post(`/customers/${customerId}/tags`, { tag_ids: tagIds });
};


// === Customer API Functions ===
// These function signatures now correctly use the imported Customer type

export const getCustomerById = async (customerId: number): Promise<Customer> => {
    const response = await apiClient.get<Customer>(`/customers/${customerId}`);
    response.data.tags = response.data.tags || [];
    return response.data;
};
export const useCustomerById = (customerId: number | null) => useSWR<Customer>(customerId ? `/customers/${customerId}` : null, fetcher);

export const getCustomersByBusiness = async (businessId: number, filterTags?: string[]): Promise<Customer[]> => {
    let url = `/customers/by-business/${businessId}`;
    if (filterTags && filterTags.length > 0) {
        url += `?tags=${filterTags.join(',')}`;
    }
    const response = await apiClient.get<Customer[]>(url);
    return response.data.map(customer => ({
        ...customer,
        tags: customer.tags || []
    }));
};
export const useCustomersByBusiness = (businessId: number | null, filterTags?: string[]) => {
    const url = businessId ? `/customers/by-business/${businessId}${filterTags && filterTags.length > 0 ? '?tags=' + filterTags.join(',') : ''}` : null;
    return useSWR<Customer[]>(url, fetcher);
};

// === Business Profile API Functions ===
export const useBusinessNavigationProfile = (businessSlug: string | null) => useSWR(businessSlug ? `/business-profile/navigation-profile/slug/${businessSlug}` : null, fetcher);
export const useBusinessIdFromSlug = (businessSlug: string | null) => useSWR(businessSlug ? `/business-profile/business-id/slug/${businessSlug}` : null, fetcher);

// === Review API Functions ===
/** @deprecated Prefer useInboxSummaries for paginated results */
export const useFullCustomerHistory = (businessId: number | null) => useSWR(businessId ? `/review/full-customer-history?business_id=${businessId}` : null, fetcher);

// === Inbox API Functions ===
// Define a type for the paginated response structure matching the backend
interface PaginatedInboxSummariesResponse {
  items: any[]; // Replace 'any' with a more specific InboxCustomerSummary type if defined on frontend
  total: number;
  page: number;
  size: number;
  pages: number;
}

export const useInboxSummaries = (businessId: number | null, page: number = 1, size: number = 20) => {
  const url = businessId ? `/review/inbox/summaries?business_id=${businessId}&page=${page}&size=${size}` : null;
  return useSWR<PaginatedInboxSummariesResponse>(url, fetcher);
};

// Type for individual messages in a conversation - should align with backend's ConversationMessageForTimeline
// and frontend's BackendMessage/TimelineEntry if possible.
export interface FrontendMessage {
  id: string | number;
  content: any; // This can be a string or a JSON object for AI messages
  created_at: string; // Assuming ISO string from backend
  sent_at?: string | null;
  scheduled_time?: string | null;
  message_type: "sent" | "customer" | "ai_draft" | "scheduled" | "scheduled_pending" | "failed_to_send" | "unknown_business_message" | "outbound_ai_reply" | string; // string for flexibility
  status?: string;
  is_hidden?: boolean;
  customer_id: number;
  business_id: number;
  // Add other fields that the backend's ConversationMessageForTimeline (derived from Message schema) might provide
}

export interface CustomerConversationResponse {
  customer_id: number;
  messages: FrontendMessage[];
  // Include pagination fields here if the backend /conversation endpoint paginates messages
}

export const useCustomerConversation = (customerId: number | null) => {
  const url = customerId ? `/customers/${customerId}/conversation` : null;
  return useSWR<CustomerConversationResponse>(url, fetcher);
};

