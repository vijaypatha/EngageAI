// frontend/src/app/profile/[business_name]/autopilot/page.tsx
"use client";

import { useEffect, useState, FormEvent, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { AxiosError } from 'axios';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch'; // Your styled switch
import { FaqCard } from '@/components/FaqCard'; 
import type { FaqItem as PageFaqItemType } from '@/components/FaqCard';
import { PlusCircle, AlertTriangle, CheckCircle2, ArrowLeft, RefreshCw, Settings } from 'lucide-react'; 

import { apiClient } from '@/lib/api';

// Backend interfaces
interface CustomFaqFromBackend {
  question: string;
  answer: string;
}

interface StructuredFaqDataFromBackend {
  operating_hours?: string | null;
  address?: string | null;
  website?: string | null;
  custom_faqs?: CustomFaqFromBackend[] | null;
}

interface BusinessProfileFromBackend {
  id: number;
  business_name: string;
  slug: string;
  enable_ai_faq_auto_reply: boolean;
  structured_faq_data?: StructuredFaqDataFromBackend | null;
}

// Frontend FAQ item type with isEditing flag
interface AutopilotPageFaqItem extends PageFaqItemType {
  isEditing?: boolean;
}

interface AutopilotPageState {
  enable_ai_faq_auto_reply: boolean;
  faqs: AutopilotPageFaqItem[]; 
}

export default function AutopilotSettingsPage() {
  const params = useParams();
  const router = useRouter();
  const businessSlug = params.business_name as string;

  const [businessId, setBusinessId] = useState<number | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const [formState, setFormState] = useState<AutopilotPageState>({
    enable_ai_faq_auto_reply: false,
    faqs: [
      { id: 'system-hours', type: 'system', questionText: 'What are your Operating Hours?', answerText: '', placeholder: 'e.g., Mon-Fri: 9am-6pm, Sat: 10am-4pm, Closed Sunday', isEditing: false },
      { id: 'system-address', type: 'system', questionText: 'What is your Business Address?', answerText: '', placeholder: 'e.g., 123 Main Street, Anytown, USA 12345', isEditing: false },
      { id: 'system-website', type: 'system', questionText: 'What is your Website URL?', answerText: '', placeholder: 'e.g., https://www.yourbusiness.com', isEditing: false },
    ],
  });
  
  const fetchProfileData = useCallback(async () => {
    if (!businessSlug) {
      setError("Business identifier (slug) not found in URL.");
      setInitialLoading(false);
      return;
    }
    setInitialLoading(true);
    setError(null);
    setSuccessMessage(null);
    try {
      const response = await apiClient.get<BusinessProfileFromBackend>(
        `/business-profile/navigation-profile/slug/${businessSlug}`
      );
      const profileData = response.data;
      
      if (profileData && profileData.id) {
        setBusinessId(profileData.id);

        const systemFaqs: AutopilotPageFaqItem[] = [
          { id: 'system-hours', type: 'system', questionText: 'What are your Operating Hours?', answerText: profileData.structured_faq_data?.operating_hours || '', placeholder: 'e.g., Mon-Fri: 9am-6pm, Sat: 10am-4pm, Closed Sunday', isEditing: false },
          { id: 'system-address', type: 'system', questionText: 'What is your Business Address?', answerText: profileData.structured_faq_data?.address || '', placeholder: 'e.g., 123 Main Street, Anytown, USA 12345', isEditing: false },
          { id: 'system-website', type: 'system', questionText: 'What is your Website URL?', answerText: profileData.structured_faq_data?.website || '', placeholder: 'e.g., https://www.yourbusiness.com', isEditing: false },
        ];

        const customFaqsFromBackend = (profileData.structured_faq_data?.custom_faqs || []).map((faq, index): AutopilotPageFaqItem => ({
          id: `custom-${profileData.id}-${index}-${Date.now()}`,
          type: 'custom',
          questionText: faq.question,
          answerText: faq.answer,
          isEditing: false,
        }));

        setFormState({
          enable_ai_faq_auto_reply: profileData.enable_ai_faq_auto_reply || false,
          faqs: [...systemFaqs, ...customFaqsFromBackend],
        });
      } else {
        setError(`Business profile not found for "${businessSlug}".`);
      }
    } catch (err) {
      const axiosError = err as AxiosError<any>;
      setError(axiosError.response?.data?.detail || `Failed to load settings for "${businessSlug}".`);
      console.error("Error fetching profile data:", err);
    } finally {
      setInitialLoading(false);
    }
  }, [businessSlug]);


  useEffect(() => {
    fetchProfileData();
  }, [fetchProfileData]);

  const toggleFaqEditState = (id: string, editing: boolean) => {
    setFormState(prev => ({
        ...prev,
        faqs: prev.faqs.map(faq => faq.id === id ? { ...faq, isEditing: editing } : { ...faq, isEditing: false }) 
    }));
  };

  const handleFaqAnswerChange = (id: string, newAnswer: string) => {
    setFormState(prev => ({
      ...prev,
      faqs: prev.faqs.map(faq => faq.id === id ? { ...faq, answerText: newAnswer, isEditing: false } : faq)
    }));
  };

  const handleFaqQuestionChange = (id: string, newQuestion: string) => {
    setFormState(prev => ({
      ...prev,
      faqs: prev.faqs.map(faq => (faq.id === id && faq.type === 'custom') ? { ...faq, questionText: newQuestion } : faq)
    }));
  };

  const addCustomFaqCard = () => {
    const newFaqId = `custom-new-${Date.now()}`;
    setFormState(prev => ({
      ...prev,
      faqs: [
        ...prev.faqs.map(f => ({...f, isEditing: false})), 
        { 
          id: newFaqId, 
          type: 'custom', 
          questionText: '', 
          answerText: '', 
          isEditing: true, 
          placeholder: 'e.g., What services do you offer?', // More specific placeholder
        }
      ]
    }));
  };

  const removeFaqCard = (idToRemove: string) => {
     if (window.confirm("Are you sure you want to remove this Q&A? This action cannot be undone.")) {
        setFormState(prev => ({
        ...prev,
        faqs: prev.faqs.filter(faq => faq.id !== idToRemove)
        }));
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!businessId) {
      setError("Business ID not available. Cannot save settings.");
      return;
    }
    setIsSaving(true);
    setError(null);
    setSuccessMessage(null);
    try {
      setFormState(prev => ({ ...prev, faqs: prev.faqs.map(f => ({...f, isEditing: false})) }));

      const structuredFaqPayload: StructuredFaqDataFromBackend = {
        operating_hours: formState.faqs.find(f => f.id === 'system-hours')?.answerText.trim() || null,
        address: formState.faqs.find(f => f.id === 'system-address')?.answerText.trim() || null,
        website: formState.faqs.find(f => f.id === 'system-website')?.answerText.trim() || null,
        custom_faqs: formState.faqs
          .filter(f => f.type === 'custom')
          .map(customFaq => ({
            question: customFaq.questionText.trim(),
            answer: customFaq.answerText.trim(),
          }))
          .filter(cf => cf.question && cf.answer), 
      };
      const payload = {
        enable_ai_faq_auto_reply: formState.enable_ai_faq_auto_reply,
        structured_faq_data: structuredFaqPayload,
      };
      await apiClient.put(`/business-profile/${businessId}`, payload);
      setSuccessMessage("Autopilot settings saved successfully!");
    } catch (err) {
      const axiosError = err as AxiosError<any>;
      setError(axiosError.response?.data?.detail || "An error occurred while saving settings.");
    } finally {
      setIsSaving(false);
      setTimeout(() => {
        setSuccessMessage(null);
        setError(null);
      }, 4000);
    }
  };

  // Consistent styling classes
  const pageBgClass = "bg-nudge-gradient";
  const cardBgClass = "bg-[#1A1D2D]";
  const cardBorderClass = "border-[#2A2F45]";
  const textPrimaryClass = "text-white";
  const textSecondaryClass = "text-gray-400";
  const textMutedClass = "text-gray-500";

  if (initialLoading) { 
    return (
      <div className={`flex flex-col justify-center items-center min-h-screen p-4 text-center ${pageBgClass}`}>
        <RefreshCw className={`animate-spin h-8 w-8 text-emerald-400 mb-3`} />
        <p className={textPrimaryClass}>Loading Autopilot Settings...</p>
      </div>
    );
  }
  if (error && !businessId) { 
    return (
      <div className={`flex flex-col justify-center items-center min-h-screen p-4 text-center ${pageBgClass}`}>
        <Card className={`max-w-md mx-auto ${cardBgClass} ${cardBorderClass} shadow-xl p-6`}>
            <CardHeader className="p-0 mb-4"><CardTitle className="text-red-400 flex items-center justify-center text-xl"><AlertTriangle className="h-6 w-6 mr-2 shrink-0" /> Error Loading</CardTitle></CardHeader>
            <CardContent className="p-0 mb-4"> <p className={textSecondaryClass}>{error}</p> </CardContent>
            <CardFooter className="p-0"> <Button onClick={() => router.back()} className={`w-full bg-emerald-500 hover:bg-emerald-600 ${textPrimaryClass}`}> <ArrowLeft className="mr-2 h-4 w-4" /> Go Back </Button></CardFooter>
        </Card>
      </div>
    );
  }

  return (
    <div className={`min-h-screen ${pageBgClass} ${textPrimaryClass} py-12 px-4 sm:px-6 lg:px-8`}>
      <div className="container mx-auto max-w-4xl">
        <Button variant="ghost" onClick={() => router.back()} className={`mb-6 text-sm ${textSecondaryClass} hover:bg-[#242842] px-3 py-1.5 rounded-md`}>
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to Profile
        </Button>
        
        <div className="text-center mb-10">
          <h1 className={`text-3xl sm:text-4xl font-bold tracking-tight ${textPrimaryClass} flex items-center justify-center`}>
            <Settings className="w-8 h-8 sm:w-10 sm:h-10 mr-3 text-emerald-400"/>
            AI Nudge Autopilot
          </h1>
          <p className={`${textSecondaryClass} mt-3 text-lg max-w-2xl mx-auto`}>
            Teach your AI Nudge. Add common Q&As, and it will handle customer inquiries for you!
          </p>
        </div>

        <div className="mb-6 space-y-3">
            {error && !successMessage && ( <div role="alert" className={`p-3 bg-red-900/40 ${cardBorderClass} border text-red-300 text-sm rounded-lg flex items-center shadow`}> <AlertTriangle className="h-5 w-5 mr-2 shrink-0" /> {error} </div> )}
            {successMessage && ( <div role="alert" className={`p-3 bg-green-900/40 ${cardBorderClass} border text-green-300 text-sm rounded-lg flex items-center shadow`}> <CheckCircle2 className="h-5 w-5 mr-2 shrink-0" /> {successMessage} </div> )}
        </div>

        <form onSubmit={handleSubmit} className="space-y-8">
          <Card className={`${cardBgClass} ${cardBorderClass} shadow-xl rounded-xl`}>
            <CardContent className="p-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div className="flex-grow">
                <Label htmlFor="enable-ai-faq-auto-reply-switch" className={`text-md font-semibold ${textPrimaryClass} block`}>
                  Enable AI Auto-Replies for FAQs
                </Label>
                <p className={`text-xs ${textSecondaryClass} mt-1`}>
                  Allow AI Nudge to use the Q&As below to automatically answer frequently asked questions.
                </p>
              </div>
              <Switch
                id="enable-ai-faq-auto-reply-switch"
                checked={formState.enable_ai_faq_auto_reply}
                onCheckedChange={(checked) => setFormState(prev => ({ ...prev, enable_ai_faq_auto_reply: checked }))}
                disabled={isSaving || initialLoading}
                className="shrink-0 data-[state=checked]:bg-emerald-500" // Consistent with other primary actions
              />
            </CardContent>
          </Card>

          <div>
            <h2 className={`text-xl font-semibold ${textPrimaryClass} mb-1`}>Knowledge Base Q&As</h2>
            <p className={`${textSecondaryClass} text-sm mb-6`}>
                Define standard responses for your business. System Q&As cover common topics; add custom ones for anything specific to your services.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {formState.faqs.map(faqItem => (
                   <FaqCard
                      key={faqItem.id}
                      className={`h-full ${cardBgClass} ${cardBorderClass} rounded-xl shadow-lg`} 
                      item={faqItem} 
                      onAnswerChange={handleFaqAnswerChange}
                      onQuestionChange={faqItem.type === 'custom' ? handleFaqQuestionChange : undefined}
                      onRemove={faqItem.type === 'custom' ? removeFaqCard : undefined}
                      isSavingOverall={isSaving || initialLoading}
                   />
              ))}
              {/* "Add Custom Q&A" Tile */}
              <Card 
                onClick={addCustomFaqCard}
                className={`h-full flex flex-col items-center justify-center text-center p-6 border-2 border-dashed ${cardBorderClass} hover:border-emerald-500 
                           cursor-pointer transition-all duration-200 
                           ${cardBgClass} hover:bg-[#242842] rounded-xl shadow-sm hover:shadow-lg group`}
                role="button"
                tabIndex={0}
                onKeyPress={(e) => { if (e.key === 'Enter' || e.key === ' ') addCustomFaqCard();}}
              >
                <PlusCircle className={`h-10 w-10 ${textMutedClass} group-hover:text-emerald-400 mb-3 transition-colors`} />
                <p className={`text-sm font-semibold ${textSecondaryClass} group-hover:${textPrimaryClass} transition-colors`}>Add Custom Q&A</p>
                <p className={`text-xs ${textMutedClass} mt-1`}>Click to add a new question and its answer.</p>
              </Card>
            </div>
          </div>
          
          <div className="pt-6 flex justify-center border-t ${cardBorderClass} mt-6">
            <Button 
                type="submit" 
                disabled={isSaving || initialLoading} 
                className="w-full sm:w-auto text-base sm:text-lg px-8 sm:px-10 py-2.5 sm:py-3 bg-gradient-to-r from-emerald-500 to-blue-600 hover:from-emerald-600 hover:to-blue-700 text-white font-semibold rounded-lg shadow-md hover:shadow-lg transition-all duration-300"
            >
              {isSaving ? <><RefreshCw className="mr-2 h-5 w-5 animate-spin"/>Saving Autopilot...</> : 'Save Autopilot Settings'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}