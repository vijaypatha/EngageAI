/* eslint-disable @typescript-eslint/no-explicit-any */
'use client';

import { useEffect, useState } from 'react';
import { apiClient } from '@/lib/api';
import { useRouter } from 'next/navigation';
// import TimelinePreview from '@/components/TimelinePreview'; // Assuming this component exists or is replaced by the direct rendering below
import { useTimezone } from '@/hooks/useTimezone';
import { getUserTimezone, US_TIMEZONES, TIMEZONE_LABELS } from '@/lib/timezone';
// REMOVED: import { calculateSendTimeUTC } from '@/lib/utils'; // No longer needed here
import OTPVerification from '@/components/OTPVerification';

// Interfaces matching backend Schemas (simplified for frontend use)
interface BusinessProfile {
  business_name: string;
  industry: string;
  business_goal: string;
  primary_services: string;
  representative_name: string;
  timezone: string;
  // business_phone_number added to OTP state instead
}

interface Customer {
  customer_name: string;
  phone: string; // Keep as string for input formatting
  lifecycle_stage: string;
  pain_points: string;
  interaction_history: string;
  timezone: string;
  // opted_in etc. handled later potentially
}

// Interface for the data stored in the frontend state for rendering
interface RoadmapMessageForState {
  id: number;
  message: string;
  send_datetime_utc: string; // Store as ISO string, matches rendering logic
  status: string;
}


interface AvailableNumber {
  phone_number: string;
  friendly_name: string;
}

interface Scenario {
  id: number; // Assuming API provides an ID
  scenario: string;
  context_type: string;
  example_response: string; // Assuming API provides an example
}

// Utility to format phone numbers consistently (+1XXXXXXXXXX)
const formatPhone = (input: string): string => {
    if (!input) return '';
    // Remove all non-digit characters except leading '+'
    const digits = input.replace(/[^\d+]/g, '');
    if (digits.startsWith('+')) {
        // Basic check for plausible length after '+'
        return digits.length >= 11 ? digits : ''; // Adjust min length as needed
    }
    // Assume US number if no '+'
    const usDigits = digits.replace(/[^0-9]/g, '');
    if (usDigits.length === 10) {
        return `+1${usDigits}`;
    }
    if (usDigits.length === 11 && usDigits.startsWith('1')) {
         return `+${usDigits}`;
    }
    // Return original digits if formatting fails, let backend validate maybe
    return digits; // Or return '' if invalid format is not allowed
};


export default function OnboardingPage() {
  const router = useRouter();
  const { businessTimezone, updateBusinessTimezone } = useTimezone();

  const [step, setStep] = useState(1);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [responses, setResponses] = useState<string[]>([]); // For style training
  const [loadingScenarios, setLoadingScenarios] = useState(false);
  const [roadmap, setRoadmap] = useState<RoadmapMessageForState[]>([]); // Use specific state type
  const [availableNumbers, setAvailableNumbers] = useState<AvailableNumber[]>([]);
  const [selectedNumber, setSelectedNumber] = useState<string>(''); // Twilio number
  const [zipCode, setZipCode] = useState<string>('');
  const [areaCode, setAreaCode] = useState<string>('');
  const [businessId, setBusinessId] = useState<number | null>(null);
  const [customerId, setCustomerId] = useState<number | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false); // General loading state
  const [error, setError] = useState<string | null>(null); // General error message

  const [businessProfile, setBusinessProfile] = useState<BusinessProfile>({
    business_name: '',
    industry: '',
    business_goal: '', // Store selected goals as comma-separated string
    primary_services: '',
    representative_name: '',
    timezone: getUserTimezone(), // Default to user's browser timezone initially
  });

  // Separate state for the user's own phone for OTP verification
   const [initialPhoneNumber, setInitialPhoneNumber] = useState('');


  const [customer, setCustomer] = useState<Customer>({
    customer_name: '',
    phone: '', // Customer's phone number
    lifecycle_stage: '',
    pain_points: '',
    interaction_history: '',
    timezone: businessProfile.timezone, // Default customer timezone to business timezone
  });

  const [previewMessage, setPreviewMessage] = useState(''); // For Step 1 sample message

  // --- Effects ---

  // Fetch sample message preview when business details change
  useEffect(() => {
    const fetchPreview = async () => {
      if (businessProfile.business_name && businessProfile.business_goal && businessProfile.industry) {
        try {
           // Ensure endpoint exists and payload matches backend expectations
          const res = await apiClient.post('/onboarding-preview/preview-message', {
            business_name: businessProfile.business_name,
            business_goal: businessProfile.business_goal,
            industry: businessProfile.industry,
            customer_name: 'Jane Doe' // Example customer name for preview
          });
          setPreviewMessage(res.data.preview);
        } catch (previewErr) {
            console.warn("Failed to fetch preview message:", previewErr);
            setPreviewMessage("Could not load preview message.");
        }
      } else {
          setPreviewMessage(""); // Clear preview if fields are empty
      }
    };
    // Debounce or throttle this if it causes too many requests
    const timer = setTimeout(fetchPreview, 300); // Simple debounce
    return () => clearTimeout(timer);

  }, [businessProfile.business_name, businessProfile.business_goal, businessProfile.industry]);

  // Update global business timezone hook when local state changes
  useEffect(() => {
    if (businessProfile.timezone) {
      updateBusinessTimezone(businessProfile.timezone);
    }
  }, [businessProfile.timezone, updateBusinessTimezone]);

  // Update default customer timezone if business timezone changes
  useEffect(() => {
    setCustomer(prev => ({ ...prev, timezone: businessProfile.timezone }));
  }, [businessProfile.timezone]);

  // Warn user before leaving if onboarding is in progress
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      // Only warn if past the first step and not during final submission/redirect
      if (step > 1 && step < 5 && !isSubmitting) {
        e.preventDefault();
        e.returnValue = 'You have unsaved progress. Are you sure you want to leave?'; // Standard browser message
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [step, isSubmitting]);


  // --- Handlers ---

    // Step 1.5 -> 2: Create Business Profile, Fetch Scenarios
    const handleBusinessSubmit = async () => {
        setIsSubmitting(true);
        setError(null);
        try {
            // 1. Create Business Profile (pass user's phone number used for OTP)
            console.log("Submitting Business Profile:", businessProfile);
            const res = await apiClient.post('/business-profile/', {
                ...businessProfile,
                // Send the phone number used for OTP verification as the initial business contact number
                business_phone_number: formatPhone(initialPhoneNumber)
            });
            const createdBusinessId = res.data.id;
            setBusinessId(createdBusinessId); // Store the ID
            console.log("Business profile created successfully:", res.data);

            // 2. Update Timezone Hook (already handled by useEffect)
            // await updateBusinessTimezone(businessProfile.timezone);

            // 3. Fetch Scenarios for Style Training
            setLoadingScenarios(true);
            try {
                console.log(`Workspaceing scenarios for business ID: ${createdBusinessId}`);
                const scenariosRes = await apiClient.get(`/sms-style/scenarios/${createdBusinessId}`);
                const fetchedScenarios = scenariosRes.data.scenarios || [];
                setScenarios(fetchedScenarios);
                setResponses(new Array(fetchedScenarios.length).fill('')); // Initialize responses array
                console.log("Scenarios fetched:", fetchedScenarios);
                setStep(2); // Move to style training step *only* after success
            } catch (scenarioErr: any) {
                console.error('Failed to fetch scenarios:', scenarioErr);
                setError(`Business profile created (ID: ${createdBusinessId}), but failed to load communication style scenarios. You can skip this for now or refresh to try again.`);
                // Decide if user should proceed without scenarios or be stuck
                 setStep(2); // Allow moving to next step even if scenarios fail? Or provide skip option? Let's allow moving.
            } finally {
                setLoadingScenarios(false);
            }
        } catch (err: any) {
            console.error('Failed to create business profile:', err);
            const errorDetail = err.response?.data?.detail || err.message || 'An unexpected error occurred.';
            setError(`Failed to create business profile: ${errorDetail}. Please check details and try again.`);
            // Stay on Step 1.5
        } finally {
            setIsSubmitting(false);
        }
    };


  // Step 2 -> 3: Submit SMS Style Responses
  const handleSmsStyleSubmit = async () => {
    if (!businessId) {
        setError("Business ID is missing. Cannot save style.");
        return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      // Construct payload ensuring all required fields for SMSStyleInput are present
      const payload = scenarios.map((scenario, i) => ({
        business_id: businessId,
        scenario: scenario.scenario,
        response: responses[i] || scenario.example_response, // Use example if no response provided? Or validate non-empty?
        context_type: scenario.context_type,
        // Provide defaults or derive from user input if available later
        tone: "professional but friendly",
        language_style: "clear and concise",
        key_phrases: [],
        formatting_preferences: {}
      }));

      console.log("Submitting SMS Style Training:", payload);
      // Assuming endpoint exists and accepts this payload structure
      await apiClient.post('/sms-style/train', payload);
      console.log("SMS Style submitted successfully.");
      setStep(3); // Move to customer input step

    } catch (err: any) {
      console.error('Failed to save SMS style:', err);
      const errorDetail = err.response?.data?.detail || err.message || 'An unexpected error occurred.';
      setError(`Failed to save your communication style: ${errorDetail}. Please try again.`);
      // Stay on Step 2
    } finally {
      setIsSubmitting(false);
    }
  };

  // Step 3 -> 4: Create Customer, Generate Roadmap
  const handleCustomerSubmit = async () => {
    if (!businessId) {
      setError("Business ID is missing. Cannot create customer.");
      return;
    }
    // Basic phone validation on frontend
    const formattedCustomerPhone = formatPhone(customer.phone);
    if (!formattedCustomerPhone) {
        setError("Please enter a valid phone number for the customer (e.g., +12223334444).");
        return;
    }

    setIsSubmitting(true);
    setError(null);
    setRoadmap([]); // Clear previous roadmap attempt

    try {
      // 1. Create Customer
      const customerPayload = {
        ...customer,
        phone: formattedCustomerPhone, // Use formatted number
        business_id: businessId,
        timezone: customer.timezone || businessProfile.timezone, // Ensure timezone
      };
      // Log before API Call
      console.log("STEP 3: Attempting to create customer and generate roadmap...");
      console.log("STEP 3: Business ID:", businessId, "Customer Data:", customerPayload);
      const customerRes = await apiClient.post('/customers/', customerPayload);
      const newCustomerId = customerRes.data.id;
      setCustomerId(newCustomerId); // Store new customer ID
      console.log("STEP 3: Customer created successfully:", customerRes.data);


      // 2. Generate Roadmap
      // Log before Roadmap API Call
      console.log("STEP 3: Requesting roadmap from /ai/roadmap...");
      const roadmapRes = await apiClient.post('/ai/roadmap', {
        business_id: businessId,
        customer_id: newCustomerId,
        // context: {} // Optional: Add extra context if needed
      });

      // Log EXACTLY what the frontend received
      console.log("STEP 3: Received API Response Status:", roadmapRes.status);
      console.log("STEP 3: Received API Response Data:", JSON.stringify(roadmapRes.data, null, 2)); // STRINGIFY TO SEE FULL STRUCTURE


      // --- Process the received API data --- // --- THIS BLOCK HAS THE 'any' PATCH ---
      const messagesFromApi = roadmapRes.data?.roadmap; // Get the roadmap array

      console.log("STEP 3: Extracted 'roadmap' key:", messagesFromApi);
      console.log("STEP 3: Is 'roadmap' key an array?", Array.isArray(messagesFromApi));

      if (Array.isArray(messagesFromApi) && messagesFromApi.length > 0) {

        // Map the received data, treating 'msg' as 'any' to bypass TS errors
        const formatted: RoadmapMessageForState[] = messagesFromApi
          .map((msg: any, index: number) => { // <<<< Use 'msg: any' here

            // Runtime check for safety (using keys from curl output)
            if (!msg || typeof msg.smsContent !== 'string' || typeof msg.send_datetime_utc !== 'string' || typeof msg.id !== 'number' || typeof msg.status !== 'string') {
              console.warn(`Skipping invalid/incomplete roadmap message item at index ${index}:`, msg);
              return null; // Skip invalid items
            }

            // Map to the state structure using the known keys from curl output
            return {
              id: msg.id,
              message: msg.smsContent, // Use smsContent received from backend
              send_datetime_utc: msg.send_datetime_utc, // Use send_datetime_utc received from backend
              status: msg.status,
            };
          })
          .filter(msg => msg !== null); // Filter out any skipped nulls

        console.log("STEP 3: Formatted data for state (using 'any'):", JSON.stringify(formatted, null, 2));

        if (formatted.length > 0) {
            console.log("STEP 3: Calling setRoadmap with formatted data...");
            setRoadmap(formatted);
            console.log("STEP 3: Calling setStep(4)...");
            setStep(4);
        } else {
            console.error("STEP 3: Formatting resulted in empty array (all items skipped), not setting state or changing step.");
            setError('Roadmap generated, but failed to process the message data.');
        }

      } else {
        // Log why it failed
        console.error("STEP 3: 'roadmap' key was not a non-empty array. Response data:", roadmapRes.data);
        setError('Failed to retrieve valid roadmap messages from the server.');
      }
     // --- END OF 'any' PATCH BLOCK ---


    } catch (err: any) {
       // Log the error that occurred in the frontend try block
       console.error('STEP 3: ERROR caught in handleCustomerSubmit:', err);
       console.error('STEP 3: Error Response Data (if available):', err.response?.data);
       setError(`Operation failed: ${err.response?.data?.detail || err.message}`);
       setRoadmap([]);
    } finally {
       console.log("STEP 3: handleCustomerSubmit finally block");
       setIsSubmitting(false);
    }
  };

   // Step 4 -> 4.5: User confirms roadmap looks good
   const handleRoadmapComplete = () => {
        if (!businessId) {
            setError("Cannot proceed without a Business ID. Please restart the onboarding or contact support.");
            return;
        }
        setInitialPhoneNumber(formatPhone(initialPhoneNumber || ''));
        setError(null);
        setStep(4.5);
    };




  // Step 5: Handle Twilio Number Search/Selection
  const handleNumberSearch = async () => {
    // Basic validation for ZIP/Area code
     if (!zipCode && !areaCode) {
          setError("Please enter a ZIP code or Area code to search.");
          return;
     }
     if (zipCode && !/^\d{5}$/.test(zipCode)) {
          setError("Please enter a valid 5-digit ZIP code.");
          return;
     }
     if (areaCode && !/^\d{3}$/.test(areaCode)) {
          setError("Please enter a valid 3-digit Area code.");
          return;
     }

    setIsSubmitting(true);
    setError(null);
    setAvailableNumbers([]); // Clear previous results
    try {
      const params = new URLSearchParams();
      if (zipCode) params.append('zip_code', zipCode);
      if (areaCode) params.append('area_code', areaCode);

      console.log(`Searching for Twilio numbers with params: ${params.toString()}`);
      // Ensure endpoint exists and returns expected structure { numbers: [...] }
      const res = await apiClient.get(`/twilio/numbers?${params.toString()}`);
      const numbers = res.data.numbers || [];
      setAvailableNumbers(numbers);
      console.log("Available Twilio numbers found:", numbers);
      if (numbers.length === 0) {
           setError("No available numbers found for this criteria. Try a different ZIP or area code.");
      }
    } catch (err: any) {
      console.error('Failed to fetch available Twilio numbers:', err);
      const errorDetail = err.response?.data?.detail || err.message || 'Failed to fetch numbers.';
      setError(`${errorDetail} Please try again.`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleNumberSelect = async (number: string) => {
     if (!businessId) {
         setError("Business ID is missing. Cannot assign number.");
         return;
     }
    setIsSubmitting(true);
    setError(null);
    try {
      setSelectedNumber(number); // Visually select the number
      console.log(`Assigning Twilio number ${number} to business ID ${businessId}`);
      // Ensure endpoint exists and assigns number, updates BusinessProfile on backend
      await apiClient.post('/twilio/assign', {
        business_id: businessId,
        phone_number: number // Backend should validate/format if needed
      });
      console.log("Twilio number assigned successfully.");

      // Fetch the business slug after assignment to redirect
      const businessRes = await apiClient.get(`/business-profile/${businessId}`);
      const slug = businessRes.data.slug;
      if (!slug) {
          console.error("Business slug not found after assigning number.");
          setError("Setup complete, but could not redirect to dashboard. Please log in manually.");
          // Maybe redirect to a generic success page or login page
          router.push('/login'); // Fallback redirect
      } else {
         console.log(`Redirecting to dashboard: /dashboard/${slug}`);
         router.push(`/dashboard/${slug}`); // Redirect to the business dashboard
      }
    } catch (err: any) {
      console.error('Failed to assign Twilio number or fetch slug:', err);
      const errorDetail = err.response?.data?.detail || err.message || 'Failed to assign number.';
      setError(`${errorDetail} Please select another number or contact support.`);
      setSelectedNumber(''); // Deselect number on error
    } finally {
      setIsSubmitting(false);
    }
  };

  // Helper for Step 1 Goal selection
  const toggleGoal = (goal: string) => {
    // Store goals as a comma-separated string
    const goals = businessProfile.business_goal ? businessProfile.business_goal.split(', ').filter(Boolean) : [];
    const updatedGoals = goals.includes(goal)
      ? goals.filter(g => g !== goal)
      : [...goals, goal];
    setBusinessProfile({ ...businessProfile, business_goal: updatedGoals.join(', ') });
  };

  // --- Render Logic ---
  // This structure assumes React allows direct rendering based on 'step' value
  // In some setups (like Next.js App Router), you might organize steps differently

  // --- Step 4 Render Function/Helper ---
  // Moved rendering logic into a separate function for clarity
  const renderStep4 = () => {
    // --- LOGGING MOVED HERE (Before Return) ---
    console.log("STEP 4: Rendering Step 4 Component");
    console.log("STEP 4: Current 'roadmap' state:", roadmap);
    console.log("STEP 4: Current 'error' state:", error);
    console.log("STEP 4: Current 'isSubmitting' state:", isSubmitting);
    // --- END LOGGING ---

    return (
      <div className="w-full rounded-xl border border-white/10 bg-gradient-to-b from-[#0C0F1F] to-[#111629] shadow-2xl p-6 sm:p-8 lg:p-10 space-y-8 backdrop-blur-sm text-white">
          {/* Removed console.logs from direct JSX */}
          <h2 className="text-3xl font-bold text-center bg-gradient-to-r from-emerald-400 to-blue-500 bg-clip-text text-transparent">
          Your AI-powered follow-up plan is ready!
          </h2>
          <p className="text-center text-gray-400 mb-6">
          Review the scheduled messages below. They will activate once setup is complete. <br/>(You can edit/disable them later in your dashboard).
          </p>
          {/* Display errors */}
          {error && <p className="text-red-400 text-center py-2">{error}</p>}

          <div className="space-y-8 max-h-[60vh] overflow-y-auto pr-2">
          {/* Loading State */}
          {isSubmitting && step === 3 ? ( // Show loading only if submitting from step 3
              <p className="text-gray-400 text-center py-10">Loading Roadmap...</p>
          ) : roadmap.length === 0 && !error ? (
              // Explicit empty state
              <p className="text-gray-400 text-center py-10">
                 No roadmap messages were generated. You can proceed and add messages manually later.
              </p>
          ) : roadmap.length > 0 && !error ? (
              // --- Render the roadmap using the state ---
              roadmap.map((msg, i) => { // msg is type RoadmapMessageForState
                 // console.log("STEP 4: Mapping message:", msg); // Keep if needed for item-level debug
                  let displayDate: Date | null = null;
                  let isValidDate = false;
                  try {
                      displayDate = new Date(msg.send_datetime_utc); // Use the UTC string from state
                      isValidDate = !isNaN(displayDate.getTime());
                  } catch (e) {
                      console.error("Error parsing date:", msg.send_datetime_utc, e);
                  }

                  const weekday = isValidDate ? displayDate?.toLocaleDateString(undefined, { weekday: 'long' }) : 'N/A';
                  const time = isValidDate ? displayDate?.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit', timeZoneName: 'short' }) : 'N/A'; // Show timezone hint
                  const month = isValidDate ? displayDate?.toLocaleString(undefined, { month: 'short' }).toUpperCase() : '??';
                  const day = isValidDate ? displayDate?.getDate() : '??';

                  return (
                  <div key={msg.id || i} className="relative border-l-4 border-purple-500 ml-8">
                      <div className="relative mb-12 pl-10 mt-12">
                      {/* Date Marker */}
                      <div className="absolute -left-6 top-1/2 transform -translate-y-1/2 flex flex-col items-center gap-1">
                          <div className="w-12 h-12 rounded-full bg-gradient-to-br from-purple-600 to-pink-500 flex flex-col items-center justify-center text-white font-bold text-xs shadow-md">
                              <span>{month}</span>
                              <span className="text-lg">{day}</span>
                          </div>
                           {/* <div className="w-px flex-1 bg-purple-500 mt-2"></div> */}
                      </div>
                      {/* Message Card */}
                      <div className="ml-4 rounded-lg shadow-md p-4 bg-zinc-800/70 border border-white/10 backdrop-blur-sm">
                          <div className="flex justify-between items-center mb-2">
                          {/* Time Display */}
                          <div className="text-base font-medium text-white/90">
                              {isValidDate ? `${weekday}, ${time}` : "Invalid Date"}
                          </div>
                          {/* Status Badge */}
                          <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded tracking-wide text-white ${
                              msg.status === 'draft' ? 'bg-yellow-600' :
                              msg.status === 'scheduled' ? 'bg-green-600' : 'bg-gray-500'
                              }`}>{msg.status || 'Unknown'}</span>
                          </div>
                           {/* Message Content */}
                          <p className="text-white/95 text-sm leading-relaxed mb-4">{msg.message}</p>
                           {/* Action Buttons (Disabled during onboarding) */}
                          <div className="flex justify-end gap-2 pt-2 border-t border-white/10">
                              <button disabled title="Editing available in dashboard" className="text-xs px-2 py-1 bg-blue-600/50 rounded text-white/70 shadow cursor-not-allowed opacity-60">Edit</button>
                              <button disabled title="Removal available in dashboard" className="text-xs px-2 py-1 bg-red-600/50 rounded text-white/70 shadow cursor-not-allowed opacity-60">Remove</button>
                          </div>
                      </div>
                      </div>
                  </div>
                  );
              })
          ) : null }
          </div>

          {/* Confirmation Button */}
           <button
              type="button"
              className="w-full mt-6 py-3 rounded-lg bg-gradient-to-r from-green-400 to-green-600 hover:opacity-90 transition-all font-semibold text-white text-lg shadow-lg disabled:opacity-50 hover:shadow-xl hover:scale-[1.02] active:scale-[0.98] disabled:hover:scale-100"
              onClick={handleRoadmapComplete} // Moves to OTP verification
              disabled={isSubmitting && step === 3} // Disable only if submitting from step 3
          >
              { error && !roadmap.length ? "Go Back & Fix" : roadmap.length > 0 ? "Looks Good! Create My Account" : "Proceed to Account Creation" }
          </button>
           <button
              type="button"
              onClick={() => setStep(3)} // Go back to customer input
              className="w-full text-sm text-gray-400 hover:text-white mt-2"
          >
              Back (Edit Customer Info)
          </button>
      </div>
    );
  };


  return (
    <div className="min-h-screen bg-[#0C0F1F] flex items-center justify-center py-8 px-4 sm:px-6 lg:px-8">
      <div className="w-full max-w-2xl space-y-6">

        {/* --- STEP 1: Basic Business Info --- */}
        {step === 1 && (
          <div className="w-full rounded-xl border border-white/10 bg-gradient-to-b from-[#0C0F1F] to-[#111629] shadow-2xl p-6 sm:p-8 lg:p-10 text-white space-y-8 backdrop-blur-sm">
            {/* Title */}
            <h1 className="text-3xl font-bold text-center bg-gradient-to-r from-emerald-400 to-blue-500 bg-clip-text text-transparent">Let's build your first nudge plan</h1>
            <p className="text-center text-gray-300 text-lg md:text-xl font-medium">Tell us about your business</p>

            <div className="space-y-6">
              {/* Business Name */}
              <input
                className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                placeholder="Business name"
                value={businessProfile.business_name}
                onChange={e => setBusinessProfile({ ...businessProfile, business_name: e.target.value })}
              />
              {/* Industry */}
              <input
                className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                placeholder="Industry (e.g. Therapy, Real Estate)"
                value={businessProfile.industry}
                onChange={e => setBusinessProfile({ ...businessProfile, industry: e.target.value })}
              />
              {/* Timezone */}
               <div className="space-y-2">
                    <p className="text-center text-gray-300 text-lg font-medium">What's your business timezone?</p>
                    <select
                        className="w-full border border-white/10 rounded-lg p-3 text-black bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                        value={businessProfile.timezone}
                        onChange={e => setBusinessProfile({ ...businessProfile, timezone: e.target.value })}
                    >
                        {US_TIMEZONES.map((tz) => (
                        <option key={tz} value={tz}>
                            {TIMEZONE_LABELS[tz] || tz}
                        </option>
                        ))}
                    </select>
                    <p className="text-sm text-gray-400 text-center">This helps us schedule messages at the right time for your business</p>
                </div>
              {/* Business Goals */}
               <div className="space-y-4">
                    <p className="text-center text-gray-300 text-lg font-medium">What do you want to achieve with nudge messaging?</p>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                        {[
                            { key: 'stay_in_touch', label: '💬 Stay in touch' },
                            { key: 'build_trust', label: '🤝 Build trust' },
                            { key: 'grow_sales', label: '📈 Grow sales' },
                            { key: 'repeat_engagement', label: '🔁 Get repeat business' },
                            { key: 'automate_followups', label: '⏱️ Save time with follow-ups' },
                            { key: 'get_referrals', label: '📣 Get more referrals' },
                        ].map(goal => (
                            <button
                            key={goal.key}
                            type="button" // Prevent form submission if wrapped in form
                            className={`aspect-square rounded-xl flex items-center justify-center text-center transition-all duration-300 p-4 hover:scale-105 ${
                                businessProfile.business_goal.includes(goal.label) // Check if label exists in string
                                ? 'bg-gradient-to-br from-emerald-400 to-blue-500 text-white shadow-lg scale-105 ring-2 ring-white/50'
                                : 'bg-[#1A1E2E] text-white/80 hover:bg-[#23283B] hover:shadow-lg'
                            }`}
                            onClick={() => toggleGoal(goal.label)}
                            >
                            <span className="text-sm md:text-base font-semibold leading-tight">{goal.label}</span>
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {/* Preview Message */}
             {businessProfile.business_name && businessProfile.business_goal && businessProfile.industry && (
                <div className="bg-[#1A1E2E]/80 backdrop-blur-sm p-4 rounded-lg border border-white/10 shadow-lg mt-6">
                    <p className="font-semibold text-sm text-white/80">
                    Here's a sample nudge {businessProfile.business_name} could use:
                    </p>
                    <div className="bg-[#111629]/90 mt-2 p-3 rounded-lg text-sm text-white/90 shadow-inner">
                    <p>{previewMessage || 'Loading preview...'}</p>
                    {/* Optional: Add opt-out text preview */}
                    {/* <p className="text-xs text-white/60 pt-2">Reply STOP to unsubscribe.</p> */}
                    </div>
                </div>
             )}

            {/* Next Button */}
            <button
              type="button"
              className="w-full mt-6 py-3 rounded-lg bg-gradient-to-r from-emerald-400 to-blue-500 hover:opacity-90 transition-all font-semibold text-white text-lg shadow-lg disabled:opacity-50 hover:shadow-xl hover:scale-[1.02] active:scale-[0.98] disabled:hover:scale-100"
              onClick={() => setStep(1.5)} // Move to next sub-step
              disabled={!businessProfile.business_name || !businessProfile.business_goal || !businessProfile.industry}
            >
              Next: Personalize Your Profile
            </button>
          </div>
        )}

        {/* --- STEP 1.5: Personalize Business --- */}
        {step === 1.5 && (
           <div className="w-full rounded-xl border border-white/10 bg-gradient-to-b from-[#0C0F1F] to-[#111629] shadow-2xl p-6 sm:p-8 lg:p-10 space-y-8 backdrop-blur-sm text-white">
            <h2 className="text-2xl font-bold text-center bg-gradient-to-r from-emerald-400 to-blue-500 bg-clip-text text-transparent">Personalize your business profile</h2>
            <p className="text-center text-gray-400 mb-6">These details help us tailor your engagement messages perfectly.</p>
             {error && <p className="text-red-400 text-center py-2">{error}</p>}
            <div className="space-y-6">
                {/* Primary Services */}
                <textarea
                    className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                    placeholder="Primary services you offer (The more details, the smarter your nudges!)"
                    value={businessProfile.primary_services}
                    onChange={e => setBusinessProfile({ ...businessProfile, primary_services: e.target.value })}
                    rows={3}
                />
                {/* Representative Name */}
                <input
                    className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                    placeholder="Your Name (used in SMS signature, e.g., 'Sarah' or 'The Team')"
                    value={businessProfile.representative_name}
                    onChange={e => setBusinessProfile({ ...businessProfile, representative_name: e.target.value })}
                />
                 {/* User's Phone Number (for OTP verification) */}
                <input
                    type="tel"
                    className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                    placeholder="Your Phone Number (for verification, e.g., +1234567890)"
                    value={initialPhoneNumber}
                    onChange={e => setInitialPhoneNumber(e.target.value)}
                />

                <button
                    type="button"
                    className="w-full mt-6 py-3 rounded-lg bg-gradient-to-r from-emerald-400 to-blue-500 hover:opacity-90 transition-all font-semibold text-white text-lg shadow-lg disabled:opacity-50 hover:shadow-xl hover:scale-[1.02] active:scale-[0.98] disabled:hover:scale-100"
                    onClick={handleBusinessSubmit} // This now creates profile AND fetches scenarios
                    disabled={isSubmitting || !businessProfile.primary_services || !businessProfile.representative_name || !formatPhone(initialPhoneNumber)}
                >
                   {isSubmitting ? 'Saving...' : 'Next: Train Your SMS Style'}
                </button>
                 <button
                    type="button"
                    onClick={() => setStep(1)}
                    className="w-full text-sm text-gray-400 hover:text-white mt-2"
                >
                    Back
                </button>
            </div>
          </div>
        )}

        {/* --- STEP 2: SMS Style Training --- */}
        {step === 2 && (
         <div className="w-full rounded-xl border border-white/10 bg-gradient-to-b from-[#0C0F1F] to-[#111629] shadow-2xl p-6 sm:p-8 lg:p-10 space-y-8 backdrop-blur-sm text-white">
            <h2 className="text-3xl font-bold text-center bg-gradient-to-r from-emerald-400 to-blue-500 bg-clip-text text-transparent">How would you respond?</h2>
            <p className="text-center text-gray-400 mb-6">Help us understand your communication style. (You can refine this later!)</p>
             {error && <p className="text-red-400 text-center py-2">{error}</p>}

            {loadingScenarios ? (
              <div className="text-center text-white py-10">
                <p>Loading scenarios...</p>
                {/* Optional: Add a spinner */}
              </div>
            ) : scenarios.length === 0 ? (
                 <div className="text-center text-gray-400 py-10">
                    <p>Could not load communication style scenarios.</p>
                    <button
                        type="button"
                         className="mt-4 px-4 py-2 rounded-lg bg-gradient-to-r from-gray-500 to-gray-700 hover:opacity-90 font-semibold text-white shadow-lg"
                        onClick={() => setStep(3)} // Allow skipping
                        >
                        Skip for Now
                    </button>
                 </div>
            ) : (
              <div className="space-y-8">
                {scenarios.map((scenario, index) => (
                  <div key={scenario.id || index} className="space-y-4">
                    {/* Scenario Description */}
                    <div className="bg-[#1A1E2E]/80 backdrop-blur-sm p-4 rounded-lg border border-white/10 shadow-lg">
                      <p className="text-white font-medium">{scenario.scenario}</p>
                       {scenario.example_response && (
                           <p className="text-sm text-gray-400 mt-2">Example: <span className="italic">{scenario.example_response}</span></p>
                       )}
                    </div>
                    {/* Response Input */}
                    <textarea
                      className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                      placeholder="Your response..."
                      value={responses[index] || ''}
                      onChange={e => {
                        const newResponses = [...responses];
                        newResponses[index] = e.target.value;
                        setResponses(newResponses);
                      }}
                      rows={3}
                      maxLength={160} // Optional: enforce SMS limit here too
                    />
                  </div>
                ))}

                <button
                    type="button"
                    className="w-full mt-6 py-3 rounded-lg bg-gradient-to-r from-emerald-400 to-blue-500 hover:opacity-90 transition-all font-semibold text-white text-lg shadow-lg disabled:opacity-50 hover:shadow-xl hover:scale-[1.02] active:scale-[0.98] disabled:hover:scale-100"
                    onClick={handleSmsStyleSubmit}
                    // Ensure all responses are filled, or allow skipping? Let's require all for now.
                    disabled={isSubmitting || responses.length !== scenarios.length || responses.some(r => !r?.trim())}
                    >
                    {isSubmitting ? 'Saving Style...' : 'Next: Add Your First Customer'}
                </button>
                 <button
                    type="button"
                    onClick={() => setStep(1.5)}
                    className="w-full text-sm text-gray-400 hover:text-white mt-2"
                >
                    Back
                </button>
              </div>
            )}
          </div>
        )}

        {/* --- STEP 3: Add First Customer --- */}
        {step === 3 && (
          <div className="w-full rounded-xl border border-white/10 bg-gradient-to-b from-[#0C0F1F] to-[#111629] shadow-2xl p-6 sm:p-8 lg:p-10 space-y-8 backdrop-blur-sm text-white">
            <h2 className="text-3xl font-bold text-center bg-gradient-to-r from-emerald-400 to-blue-500 bg-clip-text text-transparent">Who are you helping first?</h2>
            <p className="text-center text-gray-400 mb-6 text-lg">We'll use this info to create a meaningful nudge plan tailored to them.</p>
             {error && <p className="text-red-400 text-center py-2">{error}</p>}

            <div className="space-y-6">
                {/* Customer Name */}
                <input
                    className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                    placeholder="Customer Name"
                    value={customer.customer_name}
                    onChange={e => setCustomer({ ...customer, customer_name: e.target.value })}
                />
                {/* Customer Phone */}
                <input
                    type="tel"
                    className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                    placeholder="Customer Phone Number (e.g., +12223334444)"
                    value={customer.phone}
                    onChange={e => setCustomer({ ...customer, phone: e.target.value })} // Store raw input
                    onBlur={e => setCustomer({...customer, phone: formatPhone(e.target.value)})} // Format on blur
                />
                {/* Customer Timezone */}
                <div className="space-y-2">
                    <label htmlFor="customer-timezone" className="block text-sm font-medium text-white/80">
                    Customer's Timezone (Optional, defaults to yours)
                    </label>
                    <select
                    id="customer-timezone"
                    value={customer.timezone || ''} // Ensure controlled component
                    onChange={e => setCustomer({ ...customer, timezone: e.target.value })}
                    className="w-full border border-white/10 rounded-lg p-3 text-black bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                    >
                    {/* Add an option for default/business timezone */}
                    <option value={businessProfile.timezone}>Use Business Timezone ({TIMEZONE_LABELS[businessProfile.timezone] || businessProfile.timezone})</option>
                    {US_TIMEZONES.map((tz) => (
                        // Don't show the business timezone twice if it's in the US list
                        tz !== businessProfile.timezone && (
                             <option key={tz} value={tz}>
                                {TIMEZONE_LABELS[tz] || tz}
                            </option>
                        )
                    ))}
                    </select>
                    <p className="text-xs text-gray-400">Helps schedule messages appropriately for them.</p>
                </div>
                 {/* Lifecycle Stage */}
                 <div>
                    <p className="text-white font-medium mb-2">Where are they in your relationship/process?</p>
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                    {[ // Example stages, customize as needed
                        { key: "new_lead", label: "🆕 New Lead" },
                        { key: "contacted", label: "👋 Contacted" },
                        { key: "interested", label: "✅ Interested" },
                        { key: "proposal_sent", label: "✉️ Proposal Sent" },
                        { key: "getting_started", label: "🛠️ Getting Started" },
                        { key: "active_client", label: "🤝 Active Client" },
                        { key: "lost_touch", label: "📉 Lost Touch" },
                        { key: "past_client", label: "⏪ Past Client" },
                    ].map(({ key, label }) => (
                        <button
                        key={key}
                        type="button"
                        onClick={() => setCustomer({ ...customer, lifecycle_stage: label })}
                        className={`rounded-lg px-3 py-2 text-sm font-medium transition-all duration-300 hover:scale-105 ${
                            customer.lifecycle_stage === label
                            ? 'bg-gradient-to-r from-emerald-400 to-blue-500 text-white shadow-lg ring-2 ring-white/50'
                            : 'bg-[#1A1E2E] text-white/80 hover:bg-[#23283B] hover:shadow-md'
                        }`}
                        >
                        {label}
                        </button>
                    ))}
                    </div>
                </div>
                {/* Pain Points */}
                <textarea
                    className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                    placeholder="What are they struggling with? What are their goals? (Optional but helpful)"
                    value={customer.pain_points}
                    onChange={e => setCustomer({ ...customer, pain_points: e.target.value })}
                    rows={3}
                />
                {/* Interaction History */}
                <textarea
                    className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                    placeholder="Any past interactions, notes, or context? (Optional)"
                    value={customer.interaction_history}
                    onChange={e => setCustomer({ ...customer, interaction_history: e.target.value })}
                    rows={3}
                />

                {/* Submit Button */}
                <button
                    type="button"
                    className="w-full mt-6 py-3 rounded-lg bg-gradient-to-r from-emerald-400 to-blue-500 hover:opacity-90 transition-all font-semibold text-white text-lg shadow-lg disabled:opacity-50 hover:shadow-xl hover:scale-[1.02] active:scale-[0.98] disabled:hover:scale-100"
                    onClick={handleCustomerSubmit} // Creates customer AND generates roadmap
                    // Validate required fields: name, valid phone, lifecycle stage
                    disabled={isSubmitting || !customer.customer_name || !formatPhone(customer.phone) || !customer.lifecycle_stage}
                >
                    {isSubmitting ? 'Generating Roadmap...' : 'Next: Preview Your Roadmap'}
                </button>
                <button
                    type="button"
                    onClick={() => setStep(2)} // Go back to style training
                    className="w-full text-sm text-gray-400 hover:text-white mt-2"
                >
                    Back
                </button>
            </div>
          </div>
        )}

        {/* --- Render Step 4 using the helper function --- */}
        {step === 4 && renderStep4()}


        {/* --- STEP 4.5: OTP Verification --- */}
        {step === 4.5 && (
          <div className="w-full rounded-xl border border-white/10 bg-gradient-to-b from-[#0C0F1F] to-[#111629] shadow-2xl p-6 sm:p-8 lg:p-10 text-white space-y-8 backdrop-blur-sm">
            <h1 className="text-3xl font-bold text-center bg-gradient-to-r from-emerald-400 to-blue-500 bg-clip-text text-transparent">
              Secure your account
            </h1>
            <p className="text-center text-gray-300 text-lg md:text-xl font-medium">
              Verify your phone number to continue
            </p>
            
            <OTPVerification 
              initialPhoneNumber={initialPhoneNumber}
              onVerified={async (business_id, business_name) => {
                try {
                  console.log("Creating session for business ID:", business_id);
                  await apiClient.post('/auth/session', { business_id: business_id });
                  console.log("Session created successfully.");
                  setStep(5);
                } catch (err) {
                  setError("Failed to create session. Please try again.");
                }
              }}
            />

            <button
              type="button"
              onClick={() => setStep(4)}
              className="w-full text-sm text-gray-400 hover:text-white mt-4"
            >
              Back
            </button>
          </div>
        )}


        {/* --- STEP 5: Select Twilio Number --- */}
        {step === 5 && (
          <div className="w-full rounded-xl border border-white/10 bg-gradient-to-b from-[#0C0F1F] to-[#111629] shadow-2xl p-6 sm:p-8 lg:p-10 space-y-8 backdrop-blur-sm text-white">
            <h2 className="text-3xl font-bold text-center bg-gradient-to-r from-emerald-400 to-blue-500 bg-clip-text text-transparent">Choose Your Nudge Number</h2>
            <p className="text-center text-gray-400 mb-6">Select a dedicated phone number for sending and receiving nudges.</p>
             {error && (
                <div className="bg-red-900/30 border border-red-500/50 rounded-lg p-3 text-red-300 text-center text-sm">
                    {error}
                </div>
             )}

            <div className="space-y-6">
                {/* Search Inputs */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                        <label htmlFor="zip-code" className="block text-sm font-medium text-white/80 mb-1">Search by ZIP Code</label>
                        <input
                            id="zip-code"
                            className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                            placeholder="e.g., 90210"
                            value={zipCode}
                            onChange={e => { setZipCode(e.target.value.replace(/\D/g, '')); setAreaCode(''); }} // Clear area code if zip changes
                            maxLength={5}
                            pattern="[0-9]*"
                            inputMode='numeric'
                        />
                    </div>
                    <div>
                        <label htmlFor="area-code" className="block text-sm font-medium text-white/80 mb-1">Or Search by Area Code</label>
                        <input
                            id="area-code"
                            className="w-full border border-white/10 rounded-lg p-3 text-black placeholder-gray-500 bg-white/95 focus:ring-2 focus:ring-emerald-400/50 focus:border-transparent transition-all duration-200"
                            placeholder="e.g., 415"
                            value={areaCode}
                            onChange={e => { setAreaCode(e.target.value.replace(/\D/g, '')); setZipCode(''); }} // Clear zip if area code changes
                            maxLength={3}
                            pattern="[0-9]*"
                            inputMode='numeric'
                        />
                    </div>
                </div>
                {/* Search Button */}
                <button
                    type="button"
                    className="w-full mt-2 py-3 rounded-lg bg-gradient-to-r from-blue-500 to-purple-600 hover:opacity-90 transition-all font-semibold text-white text-lg shadow-lg disabled:opacity-50 hover:shadow-xl hover:scale-[1.02] active:scale-[0.98] disabled:hover:scale-100"
                    onClick={handleNumberSearch}
                    // Validate: one field must be present and have correct length
                    disabled={isSubmitting || ((!zipCode || zipCode.length !== 5) && (!areaCode || areaCode.length !== 3))}
                >
                    {isSubmitting && !availableNumbers.length ? 'Searching...' : 'Search Available Numbers'}
                </button>

                {/* Results List */}
                {isSubmitting && !availableNumbers.length && <p className='text-center text-gray-400'>Searching...</p>}
                {availableNumbers.length > 0 && (
                    <div className="space-y-3 pt-4 border-t border-white/10">
                    <p className="text-center text-gray-300 font-medium">
                        Available numbers for {zipCode ? `ZIP ${zipCode}` : `Area Code ${areaCode}`}:
                    </p>
                    <div className="max-h-[30vh] overflow-y-auto space-y-3 pr-2">
                        {availableNumbers.map((number) => (
                        <button
                            key={number.phone_number}
                            type="button"
                            className={`w-full py-3 rounded-lg transition-all font-semibold text-lg shadow-md hover:scale-[1.01] active:scale-[0.99] border-2 ${
                            selectedNumber === number.phone_number
                                ? 'bg-gradient-to-r from-emerald-400 to-blue-500 text-white border-white/50 ring-2 ring-offset-2 ring-offset-[#0C0F1F] ring-emerald-300' // Highlight selected
                                : 'bg-[#1A1E2E] text-white/80 hover:bg-[#23283B] border-transparent hover:border-white/30'
                            }`}
                            onClick={() => handleNumberSelect(number.phone_number)} // Changed from setSelectedNumber to handleNumberSelect
                            disabled={isSubmitting} // Disable while assigning
                        >
                            {number.friendly_name} {/* Display formatted number */}
                            {isSubmitting && selectedNumber === number.phone_number && ' (Assigning...)'}
                        </button>
                        ))}
                    </div>
                    </div>
                )}
                {/* No Back button here, as this is the final step before dashboard */}
            </div>
          </div>
        )}

      </div> {/* End max-w-2xl */}
    </div> // End container
  );
}