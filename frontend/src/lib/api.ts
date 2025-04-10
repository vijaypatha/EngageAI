import axios from "axios";

// ✅ Uses Render in production, localhost in dev
const baseURL = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

console.log("🚀 Using API base:", process.env.NEXT_PUBLIC_API_BASE);

export const apiClient = axios.create({
  baseURL,
  withCredentials: true, // Add this line to include credentials (cookies) in requests
});

export async function sendManualReply(customerId: number, message: string) {
  const res = await apiClient.post(`/engagements/manual-reply/${customerId}`, {
    message,
  });
  return res.data;
}

export async function getConversation(customerId: number) {
  const res = await apiClient.get(`/conversations/${customerId}`);
  return res.data;
}