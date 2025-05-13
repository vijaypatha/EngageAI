// frontend/src/app/profile/[business_name]/autopilot/page.tsx
"use client";

import { useEffect, useState, FormEvent, ChangeEvent } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { AxiosError } from 'axios';

// --- YOUR ACTUAL IMPORTS ---
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
// import { Separator } from '@/components/ui/separator'; // Uncomment if you use it
// import { PlusCircle, Trash2, AlertTriangle, CheckCircle2 } from 'lucide-react'; // Example icons

// --- YOUR ACTUAL API CLIENT ---
import { apiClient } from '@/lib/api'; // Assuming this is your configured axios instance

// --- TYPE DEFINITIONS (Should mirror backend Pydantic schemas from your app/schemas.py) ---
interface CustomFaq {
  question: string;
  answer: string;
}

interface StructuredFaqData {
  operating_hours?: string | null;
  address?: string | null;
  website?: string | null;
  custom_faqs?: CustomFaq[] | null; // Array of simple {question, answer} objects
}

interface BusinessProfile {
  id: number;
  business_name: string;
  slug: string;
  // flags from backend:
  enable_ai_faq_auto_reply: boolean;
  notify_owner_on_reply_with_link: boolean; // This flag is managed on the main profile page
  // data field:
  structured_faq_data?: StructuredFaqData | null;
  // Add any other fields your BusinessProfile API returns that might be useful
}

// For local form state, especially for custom_faqs list rendering
interface ClientCustomFaqItem extends CustomFaq {
  clientId: string; // Temporary ID for React key prop and list manipulation
}

// Local form state for this page
interface AutopilotPageState {
  enable_ai_faq_auto_reply: boolean;
  operating_hours: string;
  address: string;
  website: string;
  custom_faqs: ClientCustomFaqItem[];
}

export default function AutopilotSettingsPage() {
  const params = useParams();
  const router = useRouter();
  const businessSlug = params.business_name as string;

  const [businessId, setBusinessId] = useState<number | null>(null);
  const [currentBusinessName, setCurrentBusinessName] = useState<string>(''); // For display
  const [initialLoading, setInitialLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const [formState, setFormState] = useState<AutopilotPageState>({
    enable_ai_faq_auto_reply: false,
    operating_hours: '',
    address: '',
    website: '',
    custom_faqs: [],
  });

  useEffect(() => {
    if (!businessSlug) {
      setError("Business identifier (slug) not found in URL.");
      setInitialLoading(false);
      return;
    }

    const fetchProfileData = async () => {
      setInitialLoading(true);
      setError(null);
      setSuccessMessage(null);
      try {
        // --- CORRECTED API CALL to fetch full profile by slug ---
        const response = await apiClient.get<BusinessProfile>(
          `/business-profile/navigation-profile/slug/${businessSlug}`
        );
        const profileData = response.data;
        // --- END OF CORRECTION ---
        
        if (profileData && profileData.id) {
          setBusinessId(profileData.id);
          setCurrentBusinessName(profileData.business_name); // Store for display

          // Initialize formState based on the fetched profileData
          setFormState({
            enable_ai_faq_auto_reply: profileData.enable_ai_faq_auto_reply || false,
            operating_hours: profileData.structured_faq_data?.operating_hours || '',
            address: profileData.structured_faq_data?.address || '',
            website: profileData.structured_faq_data?.website || '',
            custom_faqs: (profileData.structured_faq_data?.custom_faqs || []).map((faq, index) => ({
              ...faq,
              clientId: `faq-${Date.now()}-${index}`, // Unique client-side ID
            })),
          });
        } else {
          setError(`Business profile not found for "${businessSlug}".`);
          console.warn("Profile data fetched by slug is missing ID or data:", profileData);
        }
      } catch (err) {
        const axiosError = err as AxiosError<any>;
        console.error("Failed to fetch business profile for autopilot:", axiosError.response?.data || axiosError.message);
        setError(axiosError.response?.data?.detail || `Failed to load settings for "${businessSlug}". Please check the slug or try again.`);
      } finally {
        setInitialLoading(false);
      }
    };

    fetchProfileData();
  }, [businessSlug]);

  const handleGenericInputChange = (field: keyof Omit<AutopilotPageState, 'custom_faqs' | 'enable_ai_faq_auto_reply'>, value: string) => {
    setFormState(prev => ({
      ...prev,
      [field]: value,
    }));
  };

  const handleCustomFaqChange = (clientId: string, field: 'question' | 'answer', value: string) => {
    setFormState(prev => ({
      ...prev,
      custom_faqs: prev.custom_faqs.map(faq =>
        faq.clientId === clientId ? { ...faq, [field]: value } : faq
      ),
    }));
  };

  const addCustomFaqPair = () => {
    setFormState(prev => ({
      ...prev,
      custom_faqs: [
        ...prev.custom_faqs,
        { clientId: `new-faq-${Date.now()}`, question: '', answer: '' },
      ],
    }));
  };

  const removeCustomFaqPair = (clientIdToRemove: string) => {
    setFormState(prev => ({
      ...prev,
      custom_faqs: prev.custom_faqs.filter(faq => faq.clientId !== clientIdToRemove),
    }));
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!businessId) {
      setError("Business ID not available. Cannot save settings.");
      setSuccessMessage(null);
      // Add user notification (e.g., toast)
      return;
    }

    setIsSaving(true);
    setError(null);
    setSuccessMessage(null);

    try {
      // This payload structure must match the BusinessProfileUpdate Pydantic schema on the backend
      const payload = {
        enable_ai_faq_auto_reply: formState.enable_ai_faq_auto_reply,
        structured_faq_data: {
          operating_hours: formState.operating_hours.trim() || null,
          address: formState.address.trim() || null,
          website: formState.website.trim() || null,
          custom_faqs: formState.custom_faqs.map(({ question, answer }) => ({ 
            question: question.trim(), 
            answer: answer.trim() 
          })).filter(faq => faq.question && faq.answer), // Filter out empty Q&As
        },
      };

      // API call to update the business profile
      // Backend has: PUT /business-profile/{business_id}
      await apiClient.put(`/business-profile/${businessId}`, payload);
      setSuccessMessage("Autopilot settings saved successfully!");
      // Example: Show toast notification for success
      // toast.success("Autopilot settings saved!");
    } catch (err) {
      const axiosError = err as AxiosError<any>;
      console.error("Failed to save autopilot settings:", axiosError.response?.data || axiosError.message);
      setError(axiosError.response?.data?.detail || "An error occurred while saving. Please try again.");
      // Example: Show toast notification for error
      // toast.error("Failed to save settings.");
    } finally {
      setIsSaving(false);
    }
  };

  if (initialLoading) {
    return (
      <div className="flex flex-col justify-center items-center min-h-screen p-4 text-center">
        {/* Replace with a proper spinner component from your library */}
        <svg className="animate-spin h-8 w-8 text-primary mb-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <p className="text-muted-foreground">Loading Autopilot Settings...</p>
      </div>
    );
  }

  if (error && !businessId && !initialLoading) { // Critical error if businessId couldn't be fetched and not loading
    return (
      <div className="container mx-auto p-4 md:p-8 text-center">
        <Card className="max-w-md mx-auto mt-10">
            <CardHeader>
                <CardTitle className="text-destructive flex items-center justify-center">
                    {/* <AlertTriangle className="h-5 w-5 mr-2" /> */}
                    Error Loading Settings
                </CardTitle>
            </CardHeader>
            <CardContent>
                <p className="text-muted-foreground">{error}</p>
            </CardContent>
            <CardFooter>
                <Button onClick={() => router.back()} className="w-full">Go Back</Button>
            </CardFooter>
        </Card>
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-3xl p-4 py-8 md:p-6 lg:p-8"> {/* Responsive padding */}
      <div className="mb-8">
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">AI Autopilot Settings</h1>
        <p className="text-muted-foreground mt-1">
          Configure AI Nudge to automatically answer common questions for <span className="font-semibold text-foreground">{currentBusinessName || businessSlug}</span>.
        </p>
      </div>

      {/* General page error (e.g., save error) */}
      {error && !successMessage && (
        <div role="alert" className="mb-6 p-4 bg-destructive/10 border border-destructive/30 text-destructive text-sm rounded-md">
            {/* <AlertTriangle className="h-4 w-4 inline mr-2" /> */}
            {error}
        </div>
      )}
      {successMessage && (
        <div role="alert" className="mb-6 p-4 bg-green-600/10 border border-green-600/30 text-green-700 dark:text-green-400 text-sm rounded-md">
            {/* <CheckCircle2 className="h-4 w-4 inline mr-2" /> */}
            {successMessage}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-8">
        <Card>
          <CardHeader>
            <CardTitle>AI Auto-Reply Status</CardTitle>
            <CardDescription>Allow AI Nudge to automatically answer frequently asked questions using the information you provide below.</CardDescription>
          </CardHeader>
          <CardContent>
          <div className="flex items-center space-x-3">
              <Switch
                id="enable-ai-faq-auto-reply-switch" // Ensure ID is unique if using 'enable-ai-faq-auto-reply' elsewhere
                checked={formState.enable_ai_faq_auto_reply}
                onCheckedChange={(checked) => setFormState(prev => ({ ...prev, enable_ai_faq_auto_reply: checked }))}
                disabled={isSaving || initialLoading}
              />
              <Label htmlFor="enable-ai-faq-auto-reply-switch" className="cursor-pointer text-sm font-medium">
                Enable AI Auto-Replies for FAQs
              </Label>
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              When enabled, AI uses the details you provide here. Auto-replies are logged in your inbox.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Business Information for AI</CardTitle>
            <CardDescription>This information helps AI Nudge answer customer questions accurately and in your brand's voice (for auto-replies).</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div>
              <Label htmlFor="operating-hours">Operating Hours</Label>
              <Textarea
                id="operating-hours"
                placeholder="e.g., Mon-Fri: 9am-6pm, Sat: 10am-4pm. Closed on Sundays and public holidays."
                value={formState.operating_hours}
                onChange={(e: ChangeEvent<HTMLTextAreaElement>) => handleGenericInputChange('operating_hours', e.target.value)}
                disabled={isSaving || initialLoading}
                rows={3}
                className="mt-1 w-full"
              />
              <p className="text-xs text-muted-foreground mt-1">Used for questions like "What are your hours?".</p>
            </div>

            <div>
              <Label htmlFor="business-address">Business Address</Label>
              <Input
                id="business-address"
                type="text"
                placeholder="e.g., 123 Main Street, Anytown, CA 90210"
                value={formState.address}
                onChange={(e: ChangeEvent<HTMLInputElement>) => handleGenericInputChange('address', e.target.value)}
                disabled={isSaving || initialLoading}
                className="mt-1 w-full"
              />
              <p className="text-xs text-muted-foreground mt-1">Used for "Where are you located?" inquiries.</p>
            </div>

            <div>
              <Label htmlFor="business-website">Website</Label>
              <Input
                id="business-website"
                type="url"
                placeholder="e.g., https://www.yourbusiness.com"
                value={formState.website}
                onChange={(e: ChangeEvent<HTMLInputElement>) => handleGenericInputChange('website', e.target.value)}
                disabled={isSaving || initialLoading}
                className="mt-1 w-full"
              />
              <p className="text-xs text-muted-foreground mt-1">Provided for website-related questions.</p>
            </div>

            {/* Optional: <Separator className="my-6" /> */}

            <div className="pt-4"> {/* Added padding-top */}
              <h3 className="text-md font-semibold mb-1 text-foreground">Custom Questions & Answers</h3>
              <p className="text-sm text-muted-foreground mb-4">Add other common questions and the specific answers AI Nudge should provide.</p>

              <div className="space-y-4">
                {formState.custom_faqs.map((faq, index) => (
                  <Card key={faq.clientId} className="p-4 bg-muted/40 shadow-sm">
                    <div className="space-y-3">
                      <div>
                        <Label htmlFor={`custom-q-${faq.clientId}`} className="text-xs font-medium text-muted-foreground">Customer Asks:</Label>
                        <Input
                          id={`custom-q-${faq.clientId}`}
                          placeholder="Enter customer's question"
                          value={faq.question}
                          onChange={(e) => handleCustomFaqChange(faq.clientId, 'question', e.target.value)}
                          disabled={isSaving || initialLoading}
                          className="mt-1 text-sm"
                        />
                      </div>
                      <div>
                        <Label htmlFor={`custom-a-${faq.clientId}`} className="text-xs font-medium text-muted-foreground">AI Nudge Should Answer:</Label>
                        <Textarea
                          id={`custom-a-${faq.clientId}`}
                          placeholder="Enter the answer AI should provide"
                          value={faq.answer}
                          onChange={(e) => handleCustomFaqChange(faq.clientId, 'answer', e.target.value)}
                          disabled={isSaving || initialLoading}
                          rows={2}
                          className="mt-1 text-sm"
                        />
                      </div>
                    </div>
                    <div className="flex justify-end mt-2">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => removeCustomFaqPair(faq.clientId)}
                        disabled={isSaving || initialLoading}
                        className="text-xs text-destructive hover:text-destructive hover:bg-destructive/10 h-7 px-2"
                      >
                        {/* <Trash2 className="h-3 w-3 mr-1" /> Optional: Icon */}
                        Remove Q&A
                      </Button>
                    </div>
                  </Card>
                ))}
                {formState.custom_faqs.length === 0 && (
                    <p className="text-xs text-muted-foreground text-center py-4 border border-dashed rounded-md">
                        No custom Q&As added yet. Click "Add Custom Q&A" to get started.
                    </p>
                )}
              </div>

              <Button
                type="button"
                variant="secondary" // Or "secondary"
                size="sm"
                className="mt-6"
                onClick={addCustomFaqPair}
                disabled={isSaving || initialLoading}
              >
                {/* <PlusCircle className="mr-2 h-4 w-4" /> Optional: Icon */}
                Add Custom Q&A
              </Button>
            </div>
          </CardContent>
          <CardFooter className="border-t pt-6 mt-6"> {/* Added mt-6 for space */}
            <Button type="submit" disabled={isSaving || initialLoading} className="w-full sm:w-auto">
              {isSaving ? 'Saving Autopilot...' : 'Save Autopilot Settings'}
            </Button>
          </CardFooter>
        </Card>
      </form>
    </div>
  );
}