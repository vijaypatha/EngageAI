"use client";

import { useState, useEffect, ChangeEvent } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiClient } from "@/lib/api";
import { SMSStyleCard } from "@/components/SMSStyleCard"; 
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
// import { Loader2 } from "lucide-react"; 

interface BusinessProfileData {
  business_name: string;
  industry: string;
  business_goal: string;
  primary_services: string;
  representative_name: string;
  twilio_number?: string;
  business_phone_number?: string;
  notify_owner_on_reply_with_link?: boolean;
}

interface FetchedBusinessProfile extends BusinessProfileData {
  id: number;
}

interface SmsStyleScenario {
  id: number; 
  scenario: string;
  context_type: string;
  response: string; 
}


export default function ProfilePage() {
  const { business_name: businessSlugFromParams } = useParams();
  const router = useRouter();
  
  const [profile, setProfile] = useState<BusinessProfileData | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editedProfile, setEditedProfile] = useState<Partial<BusinessProfileData> | null>(null);
  const [businessId, setBusinessId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true); 
  const [isSaving, setIsSaving] = useState(false); 
  const [error, setError] = useState<string | null>(null);
  const [editNotifyOwnerSms, setEditNotifyOwnerSms] = useState(false);

  const [smsStyles, setSmsStyles] = useState<SmsStyleScenario[]>([]); 
  const [isLoadingStyles, setIsLoadingStyles] = useState(false); 

  const fetchStyles = async () => { 
    if (!businessId) return;
    setIsLoadingStyles(true); 
    try {
      const res = await apiClient.get<{ scenarios: SmsStyleScenario[] }>(`/sms-style/scenarios/${businessId}`);
      setSmsStyles(res.data?.scenarios || []);
    } catch (err) {
      console.error("Failed to fetch SMS styles", err);
    } finally {
      setIsLoadingStyles(false); 
    }
  };

  useEffect(() => {
    const fetchProfileData = async () => {
      if (!businessSlugFromParams) {
        setError("Business identifier not found in URL.");
        setIsLoading(false);
        return;
      }
      setIsLoading(true);
      setError(null);
      try {
        const idRes = await apiClient.get<{ business_id: number }>(`/business-profile/business-id/slug/${businessSlugFromParams}`);
        const fetchedBusinessId = idRes.data.business_id;
        
        if (!fetchedBusinessId) {
          setError(`Profile not found for "${businessSlugFromParams}".`);
          setIsLoading(false);
          return;
        }
        setBusinessId(fetchedBusinessId); 
        
        const profileRes = await apiClient.get<FetchedBusinessProfile>(`/business-profile/${fetchedBusinessId}`);
        const fetchedData = profileRes.data;

        const displayProfileData: BusinessProfileData = {
          business_name: fetchedData.business_name,
          industry: fetchedData.industry,
          business_goal: fetchedData.business_goal,
          primary_services: fetchedData.primary_services,
          representative_name: fetchedData.representative_name,
          twilio_number: fetchedData.twilio_number,
          business_phone_number: fetchedData.business_phone_number,
          notify_owner_on_reply_with_link: fetchedData.notify_owner_on_reply_with_link || false,
        };
        
        setProfile(displayProfileData);
        setEditedProfile(displayProfileData);
        setEditNotifyOwnerSms(fetchedData.notify_owner_on_reply_with_link || false);

      } catch (err: any) {
        console.error("Failed to fetch profile:", err);
        setError(err.response?.data?.detail || "Failed to load business profile.");
      } finally {
        setIsLoading(false);
      }
    };

    fetchProfileData();
  }, [businessSlugFromParams]);

  useEffect(() => { 
    if (businessId) {
      fetchStyles();
    }
  }, [businessId]); 

  const handleInputChange = (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setEditedProfile(prev => prev ? { ...prev, [name]: value } : null);
  };

  const handleSave = async () => {
    if (!businessId || !editedProfile) {
      setError("Cannot save, profile data is missing.");
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      const payloadToUpdate = {
        ...editedProfile,
        notify_owner_on_reply_with_link: editNotifyOwnerSms,
      };
      await apiClient.put(`/business-profile/${businessId}`, payloadToUpdate);
      
      const updatedProfileData = { ...payloadToUpdate } as BusinessProfileData;
      setProfile(updatedProfileData);
      setEditNotifyOwnerSms(updatedProfileData.notify_owner_on_reply_with_link || false);
      setIsEditing(false);
      alert("Profile updated successfully!");
    } catch (err: any) {
      console.error("Failed to update profile:", err);
      setError(err.response?.data?.detail || "Failed to update profile.");
      alert("Failed to update profile.");
    } finally {
      setIsSaving(false);
    }
  };

  const toggleEditMode = () => {
    if (isEditing) {
        handleSave();
    } else {
        if (profile) {
            setEditedProfile({ ...profile });
            setEditNotifyOwnerSms(profile.notify_owner_on_reply_with_link || false);
        }
        setIsEditing(true);
    }
  };

  if (isLoading) return (
    <div className="flex justify-center items-center min-h-screen">
      <p>Loading Business Profile...</p>
    </div>
  );

  if (error && !profile) return (
    <div className="flex flex-col justify-center items-center min-h-screen text-center">
        <p className="text-red-500 text-xl mb-4">Error: {error}</p>
        <Button onClick={() => router.push('/')}>Go to Dashboard</Button>
    </div>
  );
  
  if (!profile) return (
    <div className="flex justify-center items-center min-h-screen">
      <p>Business profile could not be loaded.</p>
    </div>
  );

  const displayFields: { key: keyof BusinessProfileData; label: string; type?: string }[] = [
    { key: "business_name", label: "Business Name", type: "text" },
    { key: "industry", label: "Industry", type: "text" },
    { key: "business_goal", label: "Business Goal", type: "textarea" },
    { key: "primary_services", label: "Primary Services", type: "textarea" },
    { key: "representative_name", label: "Representative Name", type: "text" },
    { key: "twilio_number", label: "AI Nudge Number (System Assigned)", type: "text" },
    { key: "business_phone_number", label: "Your Contact Phone (for OTP & Notifications)", type: "tel" },
  ];

  return (
    <div className="min-h-screen bg-nudge-gradient text-white py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-3xl mx-auto">
        {/* Business Profile Edit Section */}
        <div className="bg-[#1A1D2D] rounded-xl border border-[#2A2F45] p-6 sm:p-8 shadow-xl">
          {/* Profile Header and Edit/Save Button */}
          <div className="flex flex-col sm:flex-row items-center justify-between mb-8 gap-4">
            <h1 className="text-2xl sm:text-3xl font-bold bg-gradient-to-r from-white to-gray-300 bg-clip-text text-transparent text-center sm:text-left">
              Business Profile
            </h1>
            <Button
              onClick={toggleEditMode}
              disabled={isSaving}
              className="px-6 py-2.5 bg-gradient-to-r from-emerald-400 to-blue-500 rounded-lg 
                text-white font-medium hover:opacity-90 transition-all duration-300 
                shadow-lg shadow-emerald-400/20 w-full sm:w-auto"
            >
              {isSaving ? "Saving..." : (isEditing ? "Save Changes" : "Edit Profile")}
            </Button>
          </div>

          {error && <p className="mb-4 text-sm text-red-500 bg-red-100/10 p-3 rounded-md">{error}</p>}

          {/* Profile Fields */}
          <div className="space-y-6">
            {displayFields.map(({ key, label, type }) => {
              const value = isEditing ? editedProfile?.[key] : profile?.[key];
              const isNonEditableSystemField = key === 'twilio_number';
              return (
                <div key={key} className="space-y-1.5">
                  <Label htmlFor={key} className="text-xs font-medium text-gray-400 block tracking-wide uppercase">
                    {label}
                  </Label>
                  {isEditing && !isNonEditableSystemField ? (
                    type === "textarea" ? (
                      <Textarea
                        id={key} name={key} value={String(value || "")} onChange={handleInputChange} rows={3}
                        className="w-full bg-[#242842] border border-[#333959] rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:border-emerald-500/70 focus:ring-1 focus:ring-emerald-500/70 transition-all duration-200 text-sm"
                      />
                    ) : (
                    <Input
                      id={key} name={key} type={type || "text"} value={String(value || "")} onChange={handleInputChange}
                      className="w-full bg-[#242842] border border-[#333959] rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:border-emerald-500/70 focus:ring-1 focus:ring-emerald-500/70 transition-all duration-200 text-sm"
                    />
                    )
                  ) : (
                    <div className={` ${isNonEditableSystemField ? 'bg-[#242842]/50 border border-[#2A2F45]/50 rounded-lg px-4 py-2.5 font-mono text-gray-500 text-sm' : 'text-base text-white/90 pt-1'} ${key === 'business_name' ? 'text-lg font-semibold' : ''} ${key === 'business_goal' && !isEditing ? 'text-base font-medium text-emerald-400/90' : ''} `}>
                      {String(value || (isEditing ? "" : "Not set"))}
                    </div>
                  )}
                </div>
              );
            })}

            {/* SMS Notification Toggle Section */}
            <div className="pt-6 mt-6 border-t border-[#2A2F45]">
              <Label className="text-base font-medium text-white/90 block mb-2">SMS Notifications</Label>
              <div className="flex items-center space-x-3 p-3 -ml-3">
                <Switch
                  id="notify-owner-sms-toggle"
                  checked={isEditing ? editNotifyOwnerSms : (profile?.notify_owner_on_reply_with_link || false)}
                  onCheckedChange={isEditing ? setEditNotifyOwnerSms : undefined}
                  disabled={!isEditing || isSaving}
                />
                <label htmlFor="notify-owner-sms-toggle" className={`text-sm ${!isEditing ? 'text-gray-500' : 'text-gray-300 cursor-pointer'} flex-1`}>
                  Notify me via SMS with an app link when a customer messages
                  <span className="block text-xs text-gray-500 mt-0.5">
                    (Applies if AI Nudge doesn't auto-reply. Notifications are sent to your contact phone above.)
                  </span>
                </label>
              </div>
            </div>
          </div>
          
          {/* Profile ID Footer (inside the main profile card) */}
          {/* <div className="mt-8 pt-6 border-t border-[#2A2F45]">
            <p className="text-xs text-gray-600 text-center">
              Profile ID: {businessId}
            </p>
          </div> */}
        </div>

        {/* --- NEW: Autopilot Settings Section --- */}
        <div className="mt-12 bg-[#1A1D2D] rounded-xl border border-[#2A2F45] p-6 sm:p-8 shadow-xl">
          <h2 className="text-xl sm:text-2xl font-bold text-white mb-4">
            AI Autopilot
          </h2>
          <p className="text-sm text-gray-400 mb-6">
            Configure AI Nudge to automatically handle common customer inquiries and more. 
            Take full control of your automated responses.
          </p>
          <div className="flex justify-center">
            <Button 
              variant="secondary"
              onClick={() => router.push(`/profile/${businessSlugFromParams}/autopilot`)}
              className="px-8 py-3 text-base sm:text-lg bg-gradient-to-r from-emerald-400 via-blue-400 to-emerald-400 rounded-lg 
                text-white font-medium hover:opacity-90 transition-all duration-300 
                shadow-lg shadow-emerald-400/20 w-full sm:w-auto max-w-md
                animate-gradient-x bg-[length:200%_100%] hover:shadow-emerald-400/40
                relative overflow-hidden before:absolute before:inset-0 before:bg-gradient-to-r 
                before:from-transparent before:via-white/20 before:to-transparent before:translate-x-[-200%]
                before:animate-shimmer"
            >
               Set AI Nudge on Autopilot, and Relax!
            </Button>
          </div>
        </div>
        {/* --- END: Autopilot Settings Section --- */}

        {/* SMS Style Section */}
        <div className="mt-12 bg-[#1A1D2D] rounded-xl border border-[#2A2F45] p-6 sm:p-8 shadow-xl">
          <h2 className="text-xl sm:text-2xl font-bold text-white mb-4">
            Refine Your AI's Voice
          </h2>
          <p className="text-sm text-gray-400 mb-6">
            AI Nudge learns from your responses to these scenarios. Provide examples of how you'd reply to help the AI perfectly match your communication style. Your changes are saved automatically when you update a response.
          </p>
          {isLoadingStyles && <p className="text-gray-400">Loading style scenarios...</p>}
          {!isLoadingStyles && smsStyles.length === 0 && (
            <p className="text-gray-400 text-center py-6 border border-dashed border-[#2A2F45] rounded-lg">
              No style training scenarios found. They may be generating.
              <br/>
              <Button variant="secondary" onClick={fetchStyles} className="text-emerald-400 hover:text-emerald-300 mt-2">
                Try refreshing scenarios
              </Button>
            </p>
          )}
          {!isLoadingStyles && smsStyles.length > 0 && (
            <div className="grid grid-cols-1 gap-6">
              {smsStyles.map((style) => (
                businessId && 
                <SMSStyleCard 
                  key={style.id} 
                  style={style} 
                  onUpdate={fetchStyles}
                  business_id={businessId} 
                />
              ))}
            </div>
          )}
        </div>
        
        {/* Logout Button */}
        <div className="flex justify-center mt-10 mb-6">
          <Button
            onClick={async () => {
              try {
                await apiClient.post('/auth/logout');
                router.push('/auth/login');
              } catch (err) {
                console.error('Logout failed:', err);
              }
            }}
            variant="destructive"
            className="px-6 py-2.5 font-medium transition duration-200 shadow-md"
          >
            Log Out
          </Button>
        </div>
      </div>
    </div>
  );
}