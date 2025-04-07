import axios from "axios";

// ✅ Uses Render in production, localhost in dev
const baseURL = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

console.log("🚀 Using API base:", process.env.NEXT_PUBLIC_API_BASE);

export const apiClient = axios.create({
  baseURL,
  withCredentials: true, // Add this line to include credentials (cookies) in requests
});
