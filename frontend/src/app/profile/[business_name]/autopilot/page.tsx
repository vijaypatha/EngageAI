// frontend/src/app/profile/[business_name]/autopilot/page.tsx
"use client";

import { useEffect, useState, FormEvent } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { AxiosError } from 'axios';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'; // Assuming Card is styled by theme or overridden
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch'; // Assuming Switch is styled by theme (e.g., accent color) or overridden
import { FaqCard } from '@/components/FaqCard';
import type { FaqItem as PageFaqItemType } from '@/components/FaqCard';
import { PlusCircle, AlertTriangle, CheckCircle2, ArrowLeft, Loader2 } from 'lucide-react'; // Added Loader2

import { apiClient } from '@/lib/api';

// Backend interfaces (assuming these are correct and don't need branding changes)
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
  const [currentBusinessName, setCurrentBusinessName] = useState<string>(''); // Retained for potential use
  const [initialLoading, setInitialLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const [formState, setFormState] = useState<AutopilotPageState>({
    enable_ai_faq_auto_reply: false,
    faqs: [
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
            id: `custom-${Date.now()}-${index}`, // Ensure unique ID generation strategy if needed
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
          setError(`Business profile not found for "${decodeURIComponent(businessSlug)}".`);
        }
      } catch (err) {
        const axiosError = err as AxiosError<any>;
        setError(axiosError.response?.data?.detail || `Failed to load settings for "${decodeURIComponent(businessSlug)}".`);
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
      setFormState(prev => ({
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
      <div className="flex flex-col justify-center items-center min-h-screen p-4 text-center bg-slate-900 text-slate-100">
        <Loader2 className="animate-spin h-10 w-10 text-purple-400 mb-4" />
        <p className="text-xl text-slate-300">Loading Autopilot Settings...</p>
      </div>
    );
  }
  
  // Error state when profile couldn't be loaded (critical error)
  if (error && !businessId && !initialLoading) { 
    return (
      <div className="min-h-screen bg-slate-900 py-8 text-slate-100 flex items-center justify-center">
        <Card className="max-w-md mx-auto bg-slate-800 border border-slate-700 shadow-xl">
            <CardHeader>
                <CardTitle className="text-red-400 flex items-center justify-center">
                    <AlertTriangle className="h-6 w-6 mr-2 shrink-0" /> Error Loading Settings
                </CardTitle>
            </CardHeader>
            <CardContent> <p className="text-slate-300">{error}</p> </CardContent>
            <CardFooter> 
                <Button 
                    onClick={() => router.back()} 
                    variant="outline"
                    className="w-full bg-slate-700 hover:bg-slate-600 border-slate-600 text-slate-100 hover:text-white"
                > 
                    <ArrowLeft className="mr-2 h-4 w-4" /> Go Back 
                </Button> 
            </CardFooter>
        </Card>
      </div>
    );
  }

  return (
    // Applied slate-900 background and default text color, font-sans assumed from global styles
    <div className="min-h-screen bg-slate-900 text-slate-100 py-8 font-sans"> 
      <div className="container mx-auto max-w-4xl p-4 md:p-6">
        <Button 
            variant="ghost" 
            onClick={() => router.back()} 
            className="mb-6 text-sm text-purple-400 hover:text-purple-300 hover:bg-slate-700/50 px-3 py-1.5"
        >
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to Profile
        </Button>
        
        <div className="text-center mb-10">
          {/* Title with gradient */}
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-pink-500">
            AI Nudge Autopilot
          </h1>
          {/* Subtitle style adjusted */}
          <p className="text-slate-400 mt-3 text-lg max-w-2xl mx-auto">
            AI Nudge is your sidekick—add Q&As and let it reply for you!
          </p>
        </div>

        {/* Alert styling adjusted for dark theme with accent colors */}
        {error && !successMessage && (
          <div role="alert" className="mb-6 p-4 bg-red-700/20 border border-red-600/50 text-red-300 text-sm rounded-lg flex items-center shadow-lg">
              <AlertTriangle className="h-5 w-5 mr-3 shrink-0 text-red-400" /> {error}
          </div>
        )}
        {successMessage && (
          <div role="alert" className="mb-6 p-4 bg-green-700/20 border border-green-600/50 text-green-300 text-sm rounded-lg flex items-center shadow-lg">
              <CheckCircle2 className="h-5 w-5 mr-3 shrink-0 text-green-400" /> {successMessage}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-8">
          {/* Card for AI Auto-Reply Toggle - styled like screenshot cards */}
          <Card className="bg-slate-800 border border-slate-700 shadow-xl rounded-xl">
            <CardContent className="p-6 flex flex-col sm:flex-row sm:items-center sm:justify-between">
              <div className="mb-4 sm:mb-0 flex-grow">
                <Label htmlFor="enable-ai-faq-auto-reply-switch" className="text-md font-semibold text-slate-100 block">
                  Enable AI Auto-Replies for FAQs
                </Label>
                <p className="text-xs text-slate-400 mt-1">
                  Allow AI Nudge to use the Q&As below to reply automatically.
                </p>
              </div>
              {/* Switch component - assuming it inherits accent color or is styled globally */}
              <Switch
                id="enable-ai-faq-auto-reply-switch"
                checked={formState.enable_ai_faq_auto_reply}
                onCheckedChange={(checked) => setFormState(prev => ({ ...prev, enable_ai_faq_auto_reply: checked }))}
                disabled={isSaving || initialLoading}
                className="shrink-0 data-[state=checked]:bg-purple-500 data-[state=unchecked]:bg-slate-600"
              />
            </CardContent>
          </Card>

          {/* Grid for FaqCards - ensure FaqCard itself is styled according to the screenshot */}
          {/* Inputs within FaqCard should be: bg-slate-700 border-slate-600 text-slate-100 focus:ring-purple-500 focus:border-purple-500 */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {formState.faqs.map(faqItem => (
                 <FaqCard // This component needs to be styled internally to match the theme.
                    key={faqItem.id}
                    // Pass necessary props, possibly including theme-related classes if FaqCard is generic
                    // For example: cardClassName="bg-slate-800 border border-slate-700 rounded-xl p-5 shadow-lg"
                    // inputClassName="bg-slate-700 border-slate-600 text-slate-100 focus:ring-purple-500 focus:border-purple-500"
                    item={faqItem}
                    onAnswerChange={handleFaqAnswerChange}
                    onQuestionChange={faqItem.type === 'custom' ? handleFaqQuestionChange : undefined}
                    onRemove={faqItem.type === 'custom' ? removeFaqCard : undefined}
                    isSavingOverall={isSaving || initialLoading}
                    initialEditing={faqItem.isEditing} 
                 />
            ))}
            {/* "Add Custom Q&A" Card - styled like screenshot cards */}
            <Card 
              onClick={addCustomFaqCard}
              className="flex flex-col items-center justify-center text-center p-4 border-2 border-dashed border-slate-600 hover:border-purple-500 cursor-pointer transition-all duration-200 min-h-[200px] sm:min-h-[240px] bg-slate-800/70 hover:bg-slate-700/90 rounded-xl shadow-lg hover:shadow-purple-500/20"
              role="button"
              tabIndex={0}
              onKeyPress={(e) => { if (e.key === 'Enter' || e.key === ' ') addCustomFaqCard();}}
            >
              <PlusCircle className="h-10 w-10 sm:h-12 sm:w-12 text-purple-400 mb-3" />
              <p className="text-sm font-medium text-slate-300">Add Custom Q&A</p>
              <p className="text-xs text-slate-400 mt-1 px-2">Click to define a new question and its answer.</p>
            </Card>
          </div>
          
          <div className="pt-8 flex justify-center border-t border-slate-700 mt-10">
            {/* Submit button with purple theme */}
            <Button 
              type="submit" 
              disabled={isSaving || initialLoading} 
              className="w-full md:w-auto text-lg px-10 py-3 bg-purple-600 hover:bg-purple-700 text-white disabled:opacity-70 flex items-center justify-center"
            >
              {isSaving && <Loader2 className="mr-2 h-5 w-5 animate-spin" />}
              {isSaving ? 'Saving Autopilot...' : 'Save Autopilot Settings'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}