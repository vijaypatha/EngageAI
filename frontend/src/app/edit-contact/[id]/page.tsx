// frontend/src/app/edit-contact/[id]/page.tsx
"use client";

import { useEffect, useState, useCallback } from "react"; // Added useCallback
import { useRouter, useParams } from "next/navigation";
import { apiClient, setCustomerTags, getCustomerById } from "@/lib/api"; // Import setCustomerTags, getCustomerById
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label"; // Import Label
import { Textarea } from "@/components/ui/textarea";
import { US_TIMEZONES, TIMEZONE_LABELS } from "@/lib/timezone";
import { Tag } from "@/types"; // Import Tag type
import { TagInput } from "@/components/ui/TagInput"; // Import TagInput component
import { Loader2 } from "lucide-react"; // Import Loader

// Interface matching the core form fields
interface ContactFormData {
  customer_name: string;
  phone: string;
  lifecycle_stage: string;
  pain_points: string;
  interaction_history: string;
  timezone: string;
  // Add other fields if they exist in your form state
}

export default function EditContactPage() {
  // --- State for Core Form ---
  const [form, setForm] = useState<ContactFormData>({
    customer_name: "",
    phone: "",
    lifecycle_stage: "",
    pain_points: "",
    interaction_history: "",
    timezone: "America/New_York", // Default
  });

  // --- State for Tags ---
  const [currentTags, setCurrentTags] = useState<Tag[]>([]);

  // --- Other State ---
  const [businessId, setBusinessId] = useState<number | null>(null); // Need businessId for TagInput
  const [isLoading, setIsLoading] = useState(false); // For API calls
  const [isFetching, setIsFetching] = useState(true); // For initial data load
  const [error, setError] = useState<string | null>(null);

  const { id: customerId } = useParams(); // Get customer ID from route params
  const router = useRouter();

  // Fetch existing contact data on load
  useEffect(() => {
    const fetchData = async () => {
        // Ensure id is a string and convert to number, handle potential array from params
        const idParam = Array.isArray(customerId) ? customerId[0] : customerId;
        const idNum = idParam ? parseInt(idParam, 10) : null;

        if (!idNum) {
             setError("Invalid Customer ID.");
             setIsFetching(false);
             return;
        }

        setIsFetching(true);
        setError(null);
        try {
            // Use the API function that includes tags
            const customer = await getCustomerById(idNum);
            setForm({
            customer_name: customer.customer_name,
            phone: customer.phone,
            lifecycle_stage: customer.lifecycle_stage,
            pain_points: customer.pain_points,
            interaction_history: customer.interaction_history,
            timezone: customer.timezone || "America/New_York",
            // set other form fields...
            });
            setCurrentTags(customer.tags || []); // Set initial tags
            setBusinessId(customer.business_id); // Store businessId
        } catch (err: any) {
            console.error("Failed to load contact", err);
            setError(err?.response?.data?.detail || err.message || "Failed to load contact data.");
        } finally {
            setIsFetching(false);
        }
    };
    fetchData();
  }, [customerId]); // Depend on customerId

  // --- Standard handleChange for form inputs ---
  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  // --- Handler for TagInput changes ---
   const handleTagsChange = useCallback((updatedTags: Tag[]) => {
     setCurrentTags(updatedTags);
   }, []);

  // --- Modified handleUpdate (now handleSubmit) ---
  const handleSubmit = async () => {
    const idParam = Array.isArray(customerId) ? customerId[0] : customerId;
    const idNum = idParam ? parseInt(idParam, 10) : null;

    if (!idNum) {
        setError("Cannot update: Invalid Customer ID.");
        return;
    }

    setIsLoading(true);
    setError(null);
    try {
      // Step 1: Update core customer details
      console.log(`Updating customer ${idNum} with data:`, form);
      // Assumes your PUT /customers/{id} endpoint takes the form data structure
      await apiClient.put(`/customers/${idNum}`, form);
      console.log("Customer details updated successfully.");

      // Step 2: Update tag associations
      const tagIds = currentTags.map(tag => tag.id);
      console.log(`Setting tags for customer ${idNum}:`, tagIds);
      await setCustomerTags(idNum, tagIds);
      console.log("Tag associations updated successfully.");

      // Step 3: Success - Navigate back
      router.back();

    } catch (err: any) {
      console.error("❌ Failed to update contact or tags:", err);
      const errorDetail = err?.response?.data?.detail || err.message || "An unexpected error occurred.";
      setError(errorDetail);
    } finally {
      setIsLoading(false);
    }
  };

  if (isFetching) {
      return <div className="flex min-h-screen bg-[#0C0F1F] items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-white" /></div>;
  }

  return (
    <div className="flex min-h-screen bg-[#0C0F1F] items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
      <div className="w-full max-w-2xl rounded-xl border border-white/10 bg-gradient-to-b from-[#0C0F1F] to-[#111629] shadow-2xl p-8 space-y-6">
        <h1 className="text-3xl font-bold text-center text-white">✏️ Edit Contact</h1>
        {/* Wrap form elements */}
        <div className="space-y-4">
           {/* --- Standard Fields --- */}
           <div>
             <Label htmlFor="customer_name" className="text-white">Full Name</Label>
             <Input id="customer_name" name="customer_name" value={form.customer_name} onChange={handleChange} className="bg-white text-black" required disabled={isLoading}/>
           </div>
           <div>
             <Label htmlFor="phone" className="text-white">Phone Number</Label>
             <Input id="phone" name="phone" value={form.phone} onChange={handleChange} className="bg-white text-black" required disabled={isLoading}/>
           </div>
           <div>
             <Label htmlFor="lifecycle_stage" className="text-white">Lifecycle Stage</Label>
             <Input id="lifecycle_stage" name="lifecycle_stage" value={form.lifecycle_stage} onChange={handleChange} className="bg-white text-black" required disabled={isLoading}/>
           </div>
           {/* ... Timezone Select ... */}
           <div className="space-y-2">
             <Label className="block text-sm font-medium text-white">Customer's Timezone</Label>
             <select name="timezone" value={form.timezone} onChange={handleChange} className="w-full border border-gray-300 rounded-md p-3 text-black bg-white" disabled={isLoading}>
               {US_TIMEZONES.map((tz) => (<option key={tz} value={tz}>{TIMEZONE_LABELS[tz]}</option>))}
             </select>
             <p className="text-sm text-gray-400">Helps us send messages at appropriate times.</p>
           </div>
           <div>
             <Label htmlFor="pain_points" className="text-white">Pain Points</Label>
             <Textarea id="pain_points" name="pain_points" value={form.pain_points} onChange={handleChange} className="bg-white text-black" disabled={isLoading}/>
           </div>
           <div>
             <Label htmlFor="interaction_history" className="text-white">Interaction History / Notes</Label>
             <Textarea id="interaction_history" name="interaction_history" value={form.interaction_history} onChange={handleChange} className="bg-white text-black" disabled={isLoading}/>
           </div>

          {/* --- Tag Input Integration --- */}
          {businessId && ( // Only render if businessId is loaded
             <div>
               <Label className="text-white">Tags</Label>
               <TagInput
                 businessId={businessId}
                 initialTags={currentTags} // Pass the loaded tags
                 onChange={handleTagsChange} // Update local state
               />
             </div>
           )}
          {!businessId && isFetching && ( // Show loading state for tags if needed
               <div><Label className="text-white">Tags</Label><div className="h-[40px] border border-input rounded-md bg-background flex items-center justify-center"><Loader2 className="h-4 w-4 animate-spin text-muted-foreground"/></div></div>
          )}
          {/* --- End Tag Input --- */}

          {/* Error Display */}
          {error && <p className="text-red-500 text-sm text-center">{error}</p>}

          {/* Action Buttons */}
          <div className="flex justify-end gap-2 pt-4">
            <Button variant="ghost" onClick={() => router.back()} className="text-white" disabled={isLoading}>
              Cancel
            </Button>
            <Button onClick={handleSubmit} className="bg-gradient-to-r from-green-400 to-blue-500 text-white" disabled={isLoading || isFetching || !businessId}>
              {isLoading ? <Loader2 className="h-4 w-4 animate-spin mr-2"/> : null}
              Save Changes
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}