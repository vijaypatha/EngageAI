// frontend/src/app/profile/[business_name]/autopilot/page.tsx
"use client";

import { useEffect, useState, FormEvent } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { AxiosError } from 'axios';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { FaqCard } from '@/components/FaqCard'; 
import type { FaqItem as PageFaqItemType } from '@/components/FaqCard'; // Import the type
import { PlusCircle, AlertTriangle, CheckCircle2, ArrowLeft } from 'lucide-react'; 

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

// Use the imported FaqItem type, potentially extending if page needs more info
interface AutopilotPageFaqItem extends PageFaqItemType {}

interface AutopilotPageState {
  enable_ai_faq_auto_reply: boolean;
  faqs: AutopilotPageFaqItem[]; 
}

export default function AutopilotSettingsPage() {
  const params = useParams();
  const router = useRouter();
  const businessSlug = params.business_name as string;

  const [businessId, setBusinessId] = useState<number | null>(null);
  const [currentBusinessName, setCurrentBusinessName] = useState<string>('');
  const [initialLoading, setInitialLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const [formState, setFormState] = useState<AutopilotPageState>({
    enable_ai_faq_auto_reply: false,
    faqs: [ // Initialize with system FAQ structures
      { id: 'system-hours', type: 'system', questionText: 'What are your Operating Hours?', answerText: '', placeholder: 'e.g., Mon-Fri: 9am-6pm, Sat: 10am-4pm...' },
      { id: 'system-address', type: 'system', questionText: 'What is your Business Address?', answerText: '', placeholder: 'e.g., 123 Main Street, Anytown...' },
      { id: 'system-website', type: 'system', questionText: 'What is your Website URL?', answerText: '', placeholder: 'e.g., https://www.yourbusiness.com' },
    ],
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
        const response = await apiClient.get<BusinessProfileFromBackend>(
          `/business-profile/navigation-profile/slug/${businessSlug}`
        );
        const profileData = response.data;
        
        if (profileData && profileData.id) {
          setBusinessId(profileData.id);
          setCurrentBusinessName(profileData.business_name);

          const systemFaqs: AutopilotPageFaqItem[] = [
            { id: 'system-hours', type: 'system', questionText: 'What are your Operating Hours?', answerText: profileData.structured_faq_data?.operating_hours || '', placeholder: 'e.g., Mon-Fri: 9am-6pm...', isEditing: false },
            { id: 'system-address', type: 'system', questionText: 'What is your Business Address?', answerText: profileData.structured_faq_data?.address || '', placeholder: 'e.g., 123 Main Street...', isEditing: false },
            { id: 'system-website', type: 'system', questionText: 'What is your Website URL?', answerText: profileData.structured_faq_data?.website || '', placeholder: 'e.g., https://www.yourbusiness.com', isEditing: false },
          ];

          const customFaqsFromBackend = (profileData.structured_faq_data?.custom_faqs || []).map((faq, index): AutopilotPageFaqItem => ({
            id: `custom-${Date.now()}-${index}`,
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
      } finally {
        setInitialLoading(false);
      }
    };
    fetchProfileData();
  }, [businessSlug]);

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
    setFormState(prev => ({
      ...prev,
      faqs: [
        ...prev.faqs,
        { 
          id: `custom-${Date.now()}`, 
          type: 'custom', 
          questionText: '', 
          answerText: '', 
          isEditing: true, 
          placeholder: 'Provide an answer...',
        }
      ]
    }));
  };

  const removeFaqCard = (idToRemove: string) => {
    setFormState(prev => ({
      ...prev,
      faqs: prev.faqs.filter(faq => faq.id !== idToRemove)
    }));
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!businessId) {
      setError("Business ID not available. Cannot save settings.");
      setSuccessMessage(null);
      return;
    }
    setIsSaving(true);
    setError(null);
    setSuccessMessage(null);
    try {
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
      setFormState(prev => ({ // Ensure isEditing flags are reset on successful save
        ...prev,
        faqs: prev.faqs.map(f => ({...f, isEditing: false})) 
      }));
    } catch (err) {
      const axiosError = err as AxiosError<any>;
      setError(axiosError.response?.data?.detail || "An error occurred while saving.");
    } finally {
      setIsSaving(false);
    }
  };

  if (initialLoading) { 
    return (
      <div className="flex flex-col justify-center items-center min-h-screen p-4 text-center">
        <svg className="animate-spin h-8 w-8 text-blue-600 dark:text-blue-400 mb-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <p className="text-slate-500 dark:text-slate-400">Loading Autopilot Settings...</p>
      </div>
    );
  }
  if (error && !businessId && !initialLoading) { 
    return (
      <div className="container mx-auto p-4 md:p-8 text-center">
        <Card className="max-w-md mx-auto mt-10 bg-white dark:bg-slate-800 shadow-lg">
            <CardHeader>
                <CardTitle className="text-red-600 dark:text-red-400 flex items-center justify-center">
                    <AlertTriangle className="h-6 w-6 mr-2 shrink-0" /> Error Loading Settings
                </CardTitle>
            </CardHeader>
            <CardContent> <p className="text-slate-600 dark:text-slate-400">{error}</p> </CardContent>
            <CardFooter> <Button onClick={() => router.back()} className="w-full"> <ArrowLeft className="mr-2 h-4 w-4" /> Go Back </Button> </CardFooter>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-100 dark:bg-slate-900 py-8">
      <div className="container mx-auto max-w-4xl p-4 md:p-6">
        <Button variant="ghost" onClick={() => router.back()} className="mb-6 text-sm text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700 px-3 py-1.5">
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to Profile
        </Button>
        
        <div className="text-center mb-10">
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-slate-900 dark:text-white">
            AI Nudge Autopilot
          </h1>
          <p className="text-slate-600 dark:text-slate-400 mt-2 text-lg max-w-2xl mx-auto">
          AI Nudge is your sidekick—add Q&As and let it reply for you!
          </p>
        </div>

        {error && !successMessage && (
          <div role="alert" className="mb-6 p-4 bg-red-100 dark:bg-red-900/30 border border-red-300 dark:border-red-500/50 text-red-700 dark:text-red-400 text-sm rounded-lg flex items-center shadow">
              <AlertTriangle className="h-5 w-5 mr-3 shrink-0" /> {error}
          </div>
        )}
        {successMessage && (
          <div role="alert" className="mb-6 p-4 bg-green-100 dark:bg-green-900/30 border border-green-300 dark:border-green-500/50 text-green-700 dark:text-green-400 text-sm rounded-lg flex items-center shadow">
              <CheckCircle2 className="h-5 w-5 mr-3 shrink-0" /> {successMessage}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-8">
          <Card className="bg-white dark:bg-slate-800/80 shadow-lg border border-slate-200 dark:border-slate-700 rounded-xl">
            <CardContent className="p-6 flex flex-col sm:flex-row sm:items-center sm:justify-between">
              <div className="mb-4 sm:mb-0 flex-grow">
                <Label htmlFor="enable-ai-faq-auto-reply-switch" className="text-md font-semibold text-slate-800 dark:text-slate-100 block">
                  Enable AI Auto-Replies for FAQs
                </Label>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                  Allow AI Nudge to use the Q&As below to reply automatically.
                </p>
              </div>
              <Switch
                id="enable-ai-faq-auto-reply-switch"
                checked={formState.enable_ai_faq_auto_reply}
                onCheckedChange={(checked) => setFormState(prev => ({ ...prev, enable_ai_faq_auto_reply: checked }))}
                disabled={isSaving || initialLoading}
                className="shrink-0"
              />
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5"> {/* Adjusted gap */}
            {formState.faqs.map(faqItem => (
                 <FaqCard
                    key={faqItem.id}
                    item={faqItem}
                    onAnswerChange={handleFaqAnswerChange}
                    onQuestionChange={faqItem.type === 'custom' ? handleFaqQuestionChange : undefined}
                    onRemove={faqItem.type === 'custom' ? removeFaqCard : undefined}
                    isSavingOverall={isSaving || initialLoading}
                    initialEditing={faqItem.isEditing} 
                 />
            ))}
            <Card 
              onClick={addCustomFaqCard}
              className="flex flex-col items-center justify-center text-center p-4 border-2 border-dashed border-slate-300 dark:border-slate-600 hover:border-blue-500 dark:hover:border-blue-400 cursor-pointer transition-all duration-200 min-h-[200px] sm:min-h-[240px] bg-slate-50 dark:bg-slate-800/50 hover:bg-slate-100 dark:hover:bg-slate-700/50 rounded-xl shadow-sm hover:shadow-md"
              role="button"
              tabIndex={0}
              onKeyPress={(e) => { if (e.key === 'Enter' || e.key === ' ') addCustomFaqCard();}}
            >
              <PlusCircle className="h-10 w-10 sm:h-12 sm:w-12 text-slate-400 dark:text-slate-500 mb-2" />
              <p className="text-sm font-medium text-slate-600 dark:text-slate-300">Add Custom Q&A</p>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 px-2">Click to define a new question and its answer.</p>
            </Card>
          </div>
          
          <div className="pt-8 flex justify-center border-t border-slate-200 dark:border-slate-700 mt-10">
            <Button type="submit" disabled={isSaving || initialLoading} className="w-full md:w-auto text-lg px-10 py-3">
              {isSaving ? 'Saving Autopilot...' : 'Save Autopilot Settings'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}