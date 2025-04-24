'use client';

import { useState, useEffect } from 'react';
import { useTimezone } from '@/hooks/useTimezone';
import { getUserTimezone } from '@/lib/timezone';
import { apiClient } from '@/lib/api';
import { useParams } from 'next/navigation';

export default function BusinessProfilePage() {
    const { businessTimezone, updateBusinessTimezone } = useTimezone();
    const { business_name } = useParams();
    const [businessId, setBusinessId] = useState<number | null>(null);
    const [formData, setFormData] = useState({
        businessName: '',
        industry: '',
        businessGoal: '',
        primaryServices: '',
        representativeName: '',
        timezone: businessTimezone || getUserTimezone(),
    });

    useEffect(() => {
        // Fetch business profile data
        const fetchProfile = async () => {
            try {
                // First get the business ID from slug
                const idRes = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
                const businessId = idRes.data.business_id;
                setBusinessId(businessId);
                
                // Then get the full profile using the ID
                const profileRes = await apiClient.get(`/business-profile/${businessId}`);
                const data = profileRes.data;
                
                setFormData(prev => ({
                    ...prev,
                    businessName: data.business_name,
                    industry: data.industry,
                    businessGoal: data.business_goal,
                    primaryServices: data.primary_services,
                    representativeName: data.representative_name,
                    timezone: data.timezone || businessTimezone || getUserTimezone()
                }));
            } catch (error) {
                console.error('Error fetching business profile:', error);
            }
        };

        if (business_name) {
            fetchProfile();
        }
    }, [businessTimezone, business_name]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        
        if (!businessId) return;
        
        try {
            const response = await apiClient.put(`/business-profile/${businessId}`, {
                business_name: formData.businessName,
                industry: formData.industry,
                business_goal: formData.businessGoal,
                primary_services: formData.primaryServices,
                representative_name: formData.representativeName,
                timezone: formData.timezone
            });

            // Update the business timezone in the context
            if (formData.timezone) {
                updateBusinessTimezone(formData.timezone);
            }
            alert('Profile updated successfully');
        } catch (error) {
            console.error('Error updating business profile:', error);
        }
    };

    return (
        <div className="min-h-screen bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
            <div className="max-w-md mx-auto">
                <h2 className="text-3xl font-bold text-center text-gray-900 mb-8">
                    Business Profile
                </h2>
                
                <form onSubmit={handleSubmit} className="space-y-6">
                    <div>
                        <label className="block text-sm font-medium text-gray-700">
                            Business Name
                        </label>
                        <input
                            type="text"
                            value={formData.businessName}
                            onChange={(e) => setFormData({ ...formData, businessName: e.target.value })}
                            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                            required
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700">
                            Industry
                        </label>
                        <input
                            type="text"
                            value={formData.industry}
                            onChange={(e) => setFormData({ ...formData, industry: e.target.value })}
                            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                            required
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700">
                            Business Goal
                        </label>
                        <textarea
                            value={formData.businessGoal}
                            onChange={(e) => setFormData({ ...formData, businessGoal: e.target.value })}
                            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                            required
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700">
                            Primary Services
                        </label>
                        <textarea
                            value={formData.primaryServices}
                            onChange={(e) => setFormData({ ...formData, primaryServices: e.target.value })}
                            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                            required
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700">
                            Representative Name
                        </label>
                        <input
                            type="text"
                            value={formData.representativeName}
                            onChange={(e) => setFormData({ ...formData, representativeName: e.target.value })}
                            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                            required
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700">
                            Business Timezone
                        </label>
                        <select
                            value={formData.timezone}
                            onChange={(e) => setFormData({ ...formData, timezone: e.target.value })}
                            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                            required
                        >
                            <option value="">Select a timezone</option>
                            {Intl.supportedValuesOf('timeZone').map((tz) => (
                                <option key={tz} value={tz}>
                                    {tz} ({new Date().toLocaleString('en-US', { timeZone: tz, timeZoneName: 'short' }).split(' ').pop()})
                                </option>
                            ))}
                        </select>
                        <p className="mt-1 text-sm text-gray-500">
                            This will be used for scheduling messages and displaying times
                        </p>
                    </div>

                    <div>
                        <button
                            type="submit"
                            className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                        >
                            Update Profile
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
} 