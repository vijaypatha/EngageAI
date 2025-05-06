// frontend/src/lib/api.ts
import axios from 'axios';
// --- Corrected Import ---
import { Customer, Tag } from '../types'; // Import BOTH Customer and Tag from your types file


// --- Existing apiClient setup ---
export const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_BASE || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000',
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

