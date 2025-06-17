// frontend/app/composer/[business_name]/page.tsx
"use client";

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { apiClient } from '@/lib/api';
import NudgeComposer from '@/components/composer/NudgeComposer';
import { Loader2, AlertCircle } from 'lucide-react';

export default function ComposerPage() {
    const { business_name } = useParams<{ business_name: string }>();
    const [businessId, setBusinessId] = useState<number | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchBusinessId = async () => {
            if (!business_name) {
                console.error("ComposerPage Error: 'business_name' slug is missing from the URL.");
                setError("Business name (slug) not found in the URL. Please check the address bar.");
                setIsLoading(false);
                return;
            }
            try {
                console.log(`ComposerPage: Attempting to fetch business ID for slug: "${business_name}"`);
                const response = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
                
                if (response.data?.business_id) {
                    const fetchedId = response.data.business_id;
                    setBusinessId(fetchedId);
                    console.log(`ComposerPage: SUCCESS! Found business ID: ${fetchedId}`);
                } else {
                    throw new Error("API response did not include a business_id.");
                }
            } catch (err: any) {
                console.error(`ComposerPage: FAILED to fetch business ID for slug "${business_name}".`, err);
                setError(err.response?.data?.detail || `Could not find a business with the slug '${business_name}'. Please verify the URL and ensure the seed script has run successfully.`);
            } finally {
                setIsLoading(false);
            }
        };

        fetchBusinessId();
    }, [business_name]);

    const handleCloseComposer = () => {
        console.log("Composer 'onClose' triggered.");
    };

    if (isLoading) {
        return (
            <div className="flex flex-col items-center justify-center h-screen bg-slate-900 text-white">
                <Loader2 className="w-10 h-10 animate-spin text-purple-400" />
                <p className="ml-4 mt-4 text-lg text-slate-300">Loading Composer...</p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex items-center justify-center h-screen bg-slate-900 text-white">
                <div className="text-center p-8 bg-slate-800 border border-red-500/30 rounded-lg max-w-lg">
                    <AlertCircle className="w-12 h-12 mb-4 text-red-500 mx-auto" />
                    <h2 className="text-xl font-semibold text-red-400">Error Loading Page</h2>
                    <p className="mt-2 text-slate-300">The composer could not be loaded.</p>
                    <p className="mt-4 text-sm bg-red-900/50 p-3 rounded-md text-red-200 font-mono">{error}</p>
                </div>
            </div>
        );
    }
    
    if (businessId) {
        return <NudgeComposer businessId={businessId} onClose={handleCloseComposer} />;
    }

    // Fallback UI to prevent a blank screen if something unexpected happens
    return (
        <div className="flex items-center justify-center h-screen bg-slate-900 text-yellow-400">
             <div className="text-center p-8 bg-slate-800 border border-yellow-500/30 rounded-lg max-w-lg">
                <AlertCircle className="w-12 h-12 mb-4 text-yellow-500 mx-auto" />
                <h2 className="text-xl font-semibold">Could not initialize Composer.</h2>
                <p className="mt-2 text-slate-300">The business ID could not be loaded, and no specific error was found.</p>
            </div>
        </div>
    );
}