// frontend/src/app/profile/[business_name]/page.tsx
"use client";

import { useState, useEffect, ChangeEvent } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiClient } from "@/lib/api";
// Removed SMSStyleCard import as we are rendering inline
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { AlertTriangle, CheckCircle2, RefreshCw } from "lucide-react"; // Added icons
import clsx from "clsx"; // For conditional classes

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
  context_type: string; // Keep if needed for display, not directly used in new design
  response: string; 
  // Add other fields from BusinessOwnerStyleRead if needed by frontend,
  // e.g., example_response, key_phrases etc. if you want to display them.
  // For now, the design focuses on 'scenario' and 'response'.
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

  // --- NEW State for inline editing SMS Styles ---
  const [editingScenarioId, setEditingScenarioId] = useState<number | null>(null);
  const [editingResponseText, setEditingResponseText] = useState<string>("");
  const [isSavingResponse, setIsSavingResponse] = useState<boolean>(false);
  const [styleUpdateError, setStyleUpdateError] = useState<string | null>(null);
  const [styleUpdateSuccess, setStyleUpdateSuccess] = useState<string | null>(null);
  // --- END NEW State ---

  const fetchStyles = async () => { 
    if (!businessId) return;
    setIsLoadingStyles(true); 
    setStyleUpdateError(null); // Clear previous errors
    setStyleUpdateSuccess(null); // Clear previous success messages
    try {
      const res = await apiClient.get<{ scenarios: SmsStyleScenario[] }>(`/sms-style/scenarios/${businessId}`);
      setSmsStyles(res.data?.scenarios || []);
    } catch (err) {
      console.error("Failed to fetch SMS styles", err);
      // Potentially set an error state for displaying styles loading failure
    } finally {
      setIsLoadingStyles(false); 
    }
  };

  useEffect(() => {
    const fetchProfileData = async () => {
      // ... (existing fetchProfileData logic remains the same) ...
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
    // ... (existing handleInputChange logic remains the same) ...
    const { name, value } = e.target;
    setEditedProfile(prev => prev ? { ...prev, [name]: value } : null);
  };

  const handleSave = async () => {
    // ... (existing handleSave logic remains the same) ...
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
      alert("Profile updated successfully!"); // Consider replacing alert with a toast notification
    } catch (err: any) {
      console.error("Failed to update profile:", err);
      setError(err.response?.data?.detail || "Failed to update profile.");
      alert("Failed to update profile."); // Consider replacing alert
    } finally {
      setIsSaving(false);
    }
  };

  const toggleEditMode = () => {
    // ... (existing toggleEditMode logic remains the same) ...
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

  // --- NEW Handler functions for SMS Style editing ---
  const handleEditResponse = (style: SmsStyleScenario) => {
    setEditingScenarioId(style.id);
    setEditingResponseText(style.response);
    setStyleUpdateError(null); // Clear previous errors
    setStyleUpdateSuccess(null);
  };

  const handleSaveResponse = async (scenarioId: number) => {
    if (!businessId) return;
    setIsSavingResponse(true);
    setStyleUpdateError(null);
    setStyleUpdateSuccess(null);
    try {
      // The API endpoint expects the response directly in the body,
      // and the `embed=True` on the FastAPI route means it should be wrapped
      // e.g. {"response": "actual response text"}
      await apiClient.put(`/sms-style/scenarios/${businessId}/${scenarioId}`, { response: editingResponseText });
      setEditingScenarioId(null);
      setEditingResponseText("");
      setStyleUpdateSuccess("Response updated successfully!");
      await fetchStyles(); // Refresh the list of styles
    } catch (err: any) {
      console.error("Failed to update SMS style response:", err);
      setStyleUpdateError(err.response?.data?.detail || "Failed to save response.");
    } finally {
      setIsSavingResponse(false);
      // Clear success/error messages after a delay
      setTimeout(() => {
        setStyleUpdateSuccess(null);
        setStyleUpdateError(null);
      }, 3000);
    }
  };
  // --- END NEW Handler functions ---


  if (isLoading) return (
    <div className="flex justify-center items-center min-h-screen bg-[#0F1221]"> {/* Consistent loading bg */}
      <RefreshCw className="animate-spin h-8 w-8 text-emerald-400" />
      <p className="ml-3 text-white">Loading Business Profile...</p>
    </div>
  );

  if (error && !profile) return (
     <div className="flex flex-col justify-center items-center min-h-screen text-center bg-[#0F1221] p-4">
        <AlertTriangle className="w-12 h-12 text-red-500 mb-4" />
        <p className="text-red-400 text-xl mb-4">Error: {error}</p>
        <Button onClick={() => router.push('/')} className="bg-emerald-500 hover:bg-emerald-600 text-white">
            Go to Dashboard
        </Button>
    </div>
  );
  
  if (!profile) return (
    <div className="flex justify-center items-center min-h-screen bg-[#0F1221] text-white">
      <p>Business profile could not be loaded.</p>
    </div>
  );

  // Base styling classes (derived from existing and availability page)
  const cardBgClass = "bg-[#1A1D2D]";
  const cardBorderClass = "border-[#2A2F45]";
  const inputBgClass = "bg-[#242842]";
  const inputBorderClass = "border-[#333959]";
  const inputFocusClass = "focus:border-emerald-500/70 focus:ring-1 focus:ring-emerald-500/70";
  const textPrimaryClass = "text-white";
  const textSecondaryClass = "text-gray-400"; // Softer than text-slate-300 for descriptions
  const textMutedClass = "text-gray-500";   // For even more muted text

  const displayFields: { key: keyof BusinessProfileData; label: string; type?: string }[] = [
    // ... (existing displayFields array remains the same) ...
    { key: "business_name", label: "Business Name", type: "text" },
    { key: "industry", label: "Industry", type: "text" },
    { key: "business_goal", label: "Business Goal", type: "textarea" },
    { key: "primary_services", label: "Primary Services", type: "textarea" },
    { key: "representative_name", label: "Representative Name", type: "text" },
    { key: "twilio_number", label: "AI Nudge Number (System Assigned)", type: "text" },
    { key: "business_phone_number", label: "Your Contact Phone (for OTP & Notifications)", type: "tel" },
  ];

  return (
    <div className={`min-h-screen bg-nudge-gradient ${textPrimaryClass} py-12 px-4 sm:px-6 lg:px-8`}>
      <div className="max-w-3xl mx-auto">
        {/* Business Profile Edit Section (remains the same) */}
        <div className={`${cardBgClass} rounded-xl ${cardBorderClass} p-6 sm:p-8 shadow-xl`}>
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
              {isSaving ? <><RefreshCw className="mr-2 h-4 w-4 animate-spin"/>Saving...</> : (isEditing ? "Save Changes" : "Edit Profile")}
            </Button>
          </div>
          {error && <p className={`mb-4 text-sm text-red-400 bg-red-900/30 ${cardBorderClass} border p-3 rounded-md`}>{error}</p>}
          <div className="space-y-6">
            {displayFields.map(({ key, label, type }) => {
              const value = isEditing ? editedProfile?.[key] : profile?.[key];
              const isNonEditableSystemField = key === 'twilio_number';
              return (
                <div key={key} className="space-y-1.5">
                  <Label htmlFor={key} className={`text-xs font-medium ${textSecondaryClass} block tracking-wide uppercase`}>
                    {label}
                  </Label>
                  {isEditing && !isNonEditableSystemField ? (
                    type === "textarea" ? (
                      <Textarea
                        id={key} name={key} value={String(value || "")} onChange={handleInputChange} rows={3}
                        className={`w-full ${inputBgClass} ${inputBorderClass} rounded-lg px-4 py-2.5 ${textPrimaryClass} placeholder-gray-500 ${inputFocusClass} transition-all duration-200 text-sm`}
                      />
                    ) : (
                    <Input
                      id={key} name={key} type={type || "text"} value={String(value || "")} onChange={handleInputChange}
                      className={`w-full ${inputBgClass} ${inputBorderClass} rounded-lg px-4 py-2.5 ${textPrimaryClass} placeholder-gray-500 ${inputFocusClass} transition-all duration-200 text-sm`}
                    />
                    )
                  ) : (
                     <div className={`text-base ${textPrimaryClass}/90 pt-1 
                      ${isNonEditableSystemField ? `${inputBgClass}/50 ${cardBorderClass}/50 rounded-lg px-4 py-2.5 font-mono text-gray-500 text-sm` : ''} 
                      ${key === 'business_name' ? 'text-lg font-semibold' : ''} 
                      ${key === 'business_goal' && !isEditing ? `text-base font-medium text-emerald-400/90` : ''} 
                     `}>
                      {String(value || (isEditing ? "" : <span className={textMutedClass}>Not set</span>))}
                    </div>
                  )}
                </div>
              );
            })}
            <div className={`pt-6 mt-6 border-t ${cardBorderClass}`}>
              <Label className={`text-base font-medium ${textPrimaryClass}/90 block mb-2`}>SMS Notifications</Label>
              <div className="flex items-center space-x-3 p-3 -ml-3">
                <Switch
                  id="notify-owner-sms-toggle"
                  checked={isEditing ? editNotifyOwnerSms : (profile?.notify_owner_on_reply_with_link || false)}
                  onCheckedChange={isEditing ? setEditNotifyOwnerSms : undefined}
                  disabled={!isEditing || isSaving}
                  className="data-[state=checked]:bg-emerald-500"
                />
                <label htmlFor="notify-owner-sms-toggle" className={`text-sm ${!isEditing ? textMutedClass : `${textSecondaryClass} cursor-pointer`} flex-1`}>
                  Notify me via SMS with an app link when a customer messages
                  <span className={`block text-xs ${textMutedClass} mt-0.5`}>
                    (Applies if AI Nudge doesn't auto-reply. Notifications are sent to your contact phone above.)
                  </span>
                </label>
              </div>
            </div>
          </div>
        </div>

        {/* Autopilot Settings Section (remains the same) */}
        <div className={`mt-12 ${cardBgClass} rounded-xl ${cardBorderClass} p-6 sm:p-8 shadow-xl`}>
          {/* ... content ... */}
          <h2 className={`text-xl sm:text-2xl font-bold ${textPrimaryClass} mb-4`}>
            AI Autopilot
          </h2>
          <p className={`text-sm ${textSecondaryClass} mb-6`}>
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
        
        {/* Availability Settings Section (remains the same) */}
        <div className={`mt-12 ${cardBgClass} rounded-xl ${cardBorderClass} p-6 sm:p-8 shadow-xl`}>
          {/* ... content ... */}
          <h2 className={`text-xl sm:text-2xl font-bold ${textPrimaryClass} mb-4`}>
            🗓️ Availability Settings
          </h2>
          <p className={`text-sm ${textSecondaryClass} mb-6`}>
            Define your working hours and availability style. This helps AI Nudge suggest suitable appointment times to your customers.
          </p>
          <div className="flex justify-center">
            <Button 
              variant="secondary"
              onClick={() => router.push(`/profile/${businessSlugFromParams}/availability`)}
              className="px-6 py-2.5 bg-gradient-to-r from-emerald-400 to-blue-500 rounded-lg 
                text-white font-medium hover:opacity-90 transition-all duration-300 
                shadow-lg shadow-emerald-400/20 w-full sm:w-auto"
            >
               Configure Your Availability
            </Button>
          </div>
        </div>

        {/* --- MODIFIED: SMS Style Section --- */}
        <div className={`mt-12 ${cardBgClass} rounded-xl ${cardBorderClass} p-6 sm:p-8 shadow-xl`}>
          <h2 className={`text-xl sm:text-2xl font-bold ${textPrimaryClass} mb-2`}>
            Refine Your AI's Voice
          </h2>
          <p className={`text-sm ${textSecondaryClass} mb-6`}>
            AI Nudge learns from your responses to these scenarios. Provide examples of how you'd reply to help the AI perfectly match your communication style.
          </p>

          {isLoadingStyles && (
            <div className="flex items-center justify-center py-10">
              <RefreshCw className={`animate-spin h-6 w-6 ${textSecondaryClass}`} />
              <p className={`ml-3 ${textSecondaryClass}`}>Loading style scenarios...</p>
            </div>
          )}

          {styleUpdateError && (
            <div role="alert" className={`mb-4 p-3 bg-red-900/30 border ${cardBorderClass} text-red-400 text-sm rounded-md flex items-center`}>
                <AlertTriangle className="h-5 w-5 mr-2 shrink-0" /> {styleUpdateError}
            </div>
          )}
          {styleUpdateSuccess && (
            <div role="alert" className={`mb-4 p-3 bg-green-900/30 border ${cardBorderClass} text-green-400 text-sm rounded-md flex items-center`}>
                <CheckCircle2 className="h-5 w-5 mr-2 shrink-0" /> {styleUpdateSuccess}
            </div>
          )}

          {!isLoadingStyles && smsStyles.length === 0 && (
            <div className={`text-center py-10 px-6 border-2 border-dashed ${cardBorderClass} rounded-lg`}>
              <p className={`${textSecondaryClass} mb-4`}>
                No style training scenarios found. They may be generating for the first time.
              </p>
              <Button 
                variant="secondary" 
                onClick={fetchStyles} 
                disabled={isLoadingStyles}
                className={`px-5 py-2.5 bg-emerald-500 hover:bg-emerald-600 ${textPrimaryClass} rounded-lg 
                  font-medium transition-all duration-300 shadow-md hover:shadow-lg w-auto`}
              >
                {isLoadingStyles ? <><RefreshCw className="mr-2 h-4 w-4 animate-spin"/>Refreshing...</> : "Refresh Scenarios"}
              </Button>
            </div>
          )}

          {!isLoadingStyles && smsStyles.length > 0 && (
            <div className="space-y-8"> {/* Vertical stack for scenarios */}
              {smsStyles.map((style, index) => (
                <div 
                  key={style.id} 
                  className={clsx(
                    "py-6", // Padding for each item
                    index < smsStyles.length - 1 ? `border-b ${cardBorderClass}` : "" // Separator line
                  )}
                >
                  <p className={`text-xs font-semibold ${textSecondaryClass} uppercase tracking-wider mb-1`}>Scenario</p>
                  <p className={`text-base ${textPrimaryClass}/95 mb-4 whitespace-pre-wrap`}>{style.scenario}</p>
                  
                  {editingScenarioId === style.id ? (
                    <div className="mt-2">
                      <Label htmlFor={`response-${style.id}`} className={`text-xs font-semibold ${textSecondaryClass} uppercase tracking-wider mb-1 block`}>
                        Your Response
                      </Label>
                      <Textarea
                        id={`response-${style.id}`}
                        value={editingResponseText}
                        onChange={(e) => setEditingResponseText(e.target.value)}
                        rows={4}
                        className={`w-full ${inputBgClass} ${inputBorderClass} rounded-lg px-4 py-2.5 ${textPrimaryClass} placeholder-gray-500 ${inputFocusClass} transition-all duration-200 text-sm mb-3`}
                        placeholder="Enter your desired response here..."
                      />
                      <div className="flex items-center gap-3 mt-1">
                        <Button 
                          onClick={() => handleSaveResponse(style.id)} 
                          size="sm" 
                          disabled={isSavingResponse}
                          className={`px-4 py-2 bg-emerald-500 hover:bg-emerald-600 ${textPrimaryClass} rounded-md text-sm font-medium transition-colors`}
                        >
                          {isSavingResponse ? <><RefreshCw className="mr-2 h-4 w-4 animate-spin"/>Saving...</> : 'Save Response'}
                        </Button>
                        <Button 
                          variant="ghost" 
                          size="sm" 
                          onClick={() => { setEditingScenarioId(null); setEditingResponseText(""); }}
                          className={`px-4 py-2 ${textSecondaryClass} hover:bg-[#2A2F45]/70 rounded-md text-sm transition-colors`}
                        >
                          Cancel
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="mt-2">
                      <p className={`text-xs font-semibold ${textSecondaryClass} uppercase tracking-wider mb-1`}>Current Response</p>
                      <div className={`text-sm ${textPrimaryClass}/90 mb-3 p-3 ${inputBgClass}/50 ${cardBorderClass} rounded-md min-h-[60px] whitespace-pre-wrap`}>
                        {style.response ? style.response : <p className={`italic ${textMutedClass}`}>No response yet. Click "Edit Response" to provide one.</p>}
                      </div>
                      <Button 
                        variant="secondary" 
                        size="sm" 
                        onClick={() => handleEditResponse(style)}
                        className={`px-4 py-2 ${inputBgClass} hover:bg-[#333959] ${textSecondaryClass} hover:text-white ${inputBorderClass} rounded-md text-sm font-medium transition-colors`}
                      >
                        Edit Response
                      </Button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
        {/* --- END MODIFIED: SMS Style Section --- */}
        
        {/* Logout Button (remains the same) */}
        <div className="flex justify-center mt-10 mb-6">
          {/* ... content ... */}
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