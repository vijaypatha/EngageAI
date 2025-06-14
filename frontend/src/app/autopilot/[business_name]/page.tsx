// frontend/src/app/autopilot/[business_name]/page.tsx
"use client";

//
// --- Imports ---
//
import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { apiClient } from '@/lib/api';
import AutopilotPlanView from '@/components/autopilot/AutopilotPlanView';
import { Loader2, AlertCircle } from 'lucide-react';

//
// --- Component ---
// This is the main entry point for the Autopilot page. Its primary responsibility
// is to translate the URL's `business_name` (slug) into a valid `businessId`.
// Once the ID is fetched, it renders the main view component.
//
export default function AutopilotPage() {
    //
    // --- State Management ---
    //
    const [businessId, setBusinessId] = useState<number | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    
    // Get the dynamic `business_name` slug from the URL
    const params = useParams<{ business_name: string }>();
    const businessSlug = params.business_name;

    //
    // --- Data Fetching Effect ---
    //
    useEffect(() => {
        // This function fetches the business ID using the slug.
        const fetchBusinessId = async () => {
            if (!businessSlug) {
                setError("Business name not found in URL.");
                setIsLoading(false);
                return;
            }

            // Reset state for a new fetch
            setIsLoading(true);
            setError(null);

            try {
                // Use the correct API endpoint from your backend routes
                const response = await apiClient.get(`/business-profile/business-id/slug/${businessSlug}`);
                if (response.data?.business_id) {
                    setBusinessId(response.data.business_id);
                } else {
                    // This case handles a valid API response that doesn't include the ID
                    throw new Error("API did not return a valid business ID.");
                }

            } catch (err: any) {
                // This catches network errors or 404s from the API call
                console.error("Failed to fetch business ID:", err);
                setError(err.response?.data?.detail || "Could not find the specified business.");
            } finally {
                setIsLoading(false);
            }
        };

        fetchBusinessId();
    }, [businessSlug]); // Re-run this effect if the slug in the URL changes

    //
    // --- Render Logic ---
    //
    // 1. Loading State
    if (isLoading) {
        return (
            <div className="flex h-screen w-full items-center justify-center bg-slate-900">
                <Loader2 className="h-8 w-8 animate-spin text-purple-400" />
            </div>
        );
    }

    // 2. Error State
    if (error) {
        return (
            <div className="flex h-screen w-full flex-col items-center justify-center bg-slate-900 p-4 text-center">
                <AlertCircle className="h-12 w-12 text-red-500" />
                <h2 className="mt-4 text-xl font-semibold text-white">Error Loading Autopilot</h2>
                <p className="mt-1 text-red-400">{error}</p>
            </div>
        );
    }

    // 3. Success State
    return (
        <div className="bg-slate-900">
            {businessId && businessSlug ? (
                <AutopilotPlanView businessId={businessId} businessSlug={businessSlug} />
            ) : (
                // This renders if loading is done but for some reason we still don't have an ID
                <div className="flex h-screen w-full items-center justify-center bg-slate-900 text-slate-500">
                    <p>Business information could not be loaded.</p>
                </div>
            )}
        </div>
    );
}