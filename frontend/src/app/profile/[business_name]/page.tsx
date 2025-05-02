"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiClient } from "@/lib/api";
import { SMSStyleCard } from "@/components/SMSStyleCard";
import { Button } from "@/components/ui/button";

interface BusinessProfile {
  business_name: string;
  industry: string;
  business_goal: string;
  primary_services: string;
  representative_name: string;
  twilio_number?: string;
  business_id?: number;
}

export default function ProfilePage() {
  const { business_name } = useParams();
  const router = useRouter(); 
  const [profile, setProfile] = useState<BusinessProfile | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editedProfile, setEditedProfile] = useState<BusinessProfile | null>(null);
  const [businessId, setBusinessId] = useState<number | null>(null);

  const [smsStyles, setSmsStyles] = useState<any[]>([]);

  const fetchStyles = async () => {
    if (!businessId) return;
    try {
      const res = await apiClient.get(`/sms-style/scenarios/${businessId}`);
      setSmsStyles(res.data?.scenarios || []);;
    } catch (err) {
      console.error("Failed to fetch SMS styles", err);
    }
  };

  useEffect(() => {
    const fetchProfile = async () => {
      try {
        // First get the business ID from slug
        const idRes = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
        const businessId = idRes.data.business_id;
        setBusinessId(businessId);
        
        // Then get the full profile using the ID
        const profileRes = await apiClient.get(`/business-profile/${businessId}`);
        
        // Create a cleaned profile object without id and slug
        const cleanedProfile = {
          business_name: profileRes.data.business_name,
          industry: profileRes.data.industry,
          business_goal: profileRes.data.business_goal,
          primary_services: profileRes.data.primary_services,
          representative_name: profileRes.data.representative_name,
          twilio_number: profileRes.data.twilio_number,
        };
        
        setProfile(cleanedProfile);
        setEditedProfile(cleanedProfile);
      } catch (error) {
        console.error("Failed to fetch profile:", error);
      }
    };

    fetchProfile();
  }, [business_name]);

  useEffect(() => {
    if (businessId) fetchStyles();
  }, [businessId]);

  const handleSave = async () => {
    try {
      if (!businessId) return;
      await apiClient.put(`/business-profile/${businessId}`, editedProfile);
      setProfile(editedProfile);
      setIsEditing(false);
    } catch (error) {
      console.error("Failed to update profile:", error);
    }
  };

  if (!profile) return <div>Loading...</div>;

  // Define which fields to display and their labels
  const displayFields = {
    business_name: "Business Name",
    industry: "Industry",
    business_goal: "Business Goal",
    primary_services: "Primary Services",
    representative_name: "Representative Name",
    twilio_number: "AI Nudge Number"
  };

  return (
    <div className="min-h-screen bg-nudge-gradient text-white py-12 px-6">
      <div className="max-w-3xl mx-auto">
        <div className="bg-[#1A1D2D] rounded-xl border border-[#2A2F45] p-8 shadow-xl">
          <div className="flex items-center justify-between mb-8">
            <h1 className="text-3xl font-bold bg-gradient-to-r from-white to-gray-300 bg-clip-text text-transparent">
              Business Profile
            </h1>
            <button
              onClick={() => isEditing ? handleSave() : setIsEditing(true)}
              className="px-6 py-2.5 bg-gradient-to-r from-emerald-400 to-blue-500 rounded-lg 
                text-white font-medium hover:opacity-90 transition-all duration-300 
                shadow-lg shadow-emerald-400/10"
            >
              {isEditing ? "Save Changes" : "Edit Profile"}
            </button>
          </div>

          <div className="space-y-8">
            {Object.entries(displayFields).map(([key, label]) => {
              if (!(key in profile)) return null;
              const value = profile[key as keyof BusinessProfile];
              const isAINudgeNumber = key === 'twilio_number';

              return (
                <div key={key} className="space-y-2">
                  <label className="text-sm font-medium text-gray-400 block tracking-wide uppercase">
                    {label}
                  </label>
                  {isEditing && !isAINudgeNumber ? (
                    <input
                      type="text"
                      value={editedProfile?.[key as keyof BusinessProfile] || ""}
                      onChange={(e) => setEditedProfile(prev => ({
                        ...prev!,
                        [key]: e.target.value
                      }))}
                      className="w-full bg-[#242842] border border-[#2A2F45] rounded-lg px-4 py-3 
                        text-white placeholder-gray-500 focus:border-emerald-500/50 
                        focus:ring-1 focus:ring-emerald-500/50 transition-all duration-200"
                    />
                  ) : (
                    <div className={`
                      ${isAINudgeNumber 
                        ? 'bg-[#242842] border border-[#2A2F45] rounded-lg px-4 py-3 font-mono text-gray-400' 
                        : 'text-lg text-white/90'
                      }
                      ${key === 'business_name' ? 'text-xl font-semibold' : ''}
                      ${key === 'business_goal' ? 'text-lg font-medium text-emerald-400' : ''}
                    `}>
                      {value || "Not set"}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Optional: Add a subtle gradient border at the bottom */}
          <div className="mt-8 pt-8 border-t border-[#2A2F45]">
            <p className="text-sm text-gray-500">
              Last updated: {new Date().toLocaleDateString()}
            </p>
          </div>
        </div>

        <div className="mt-12 bg-[#1A1D2D] rounded-xl border border-[#2A2F45] p-8 shadow-xl">
          <h2 className="text-2xl font-bold text-white mb-6">Your SMS Style</h2>
          <p className="text-sm text-gray-400 mb-4">
          Updates to your style will be reflected in future AI-generated messages.
          </p>
          {smsStyles.length === 0 ? (
            <p className="text-gray-400">No styles found.</p>
          ) : (
            <div className="grid grid-cols-1 gap-6">
              {smsStyles.map((style) => (
                businessId && <SMSStyleCard key={style.id} style={style} onUpdate={fetchStyles} business_id={businessId} />
              ))}
            </div>
          )}
        </div>
        
        <div className="flex justify-center mt-10">
          <button
            onClick={async () => {
              try {
                await apiClient.post('/auth/logout');
                localStorage.clear();
                router.push('/auth/login');
              } catch (err) {
                console.error('Logout failed:', err);
              }
            }}
            className="px-6 py-2.5 bg-red-600 text-white rounded-lg font-medium hover:bg-red-500 transition duration-200 shadow-md"
          >
            Log Out
          </button>
        </div>




      </div>
    </div>
  );
}