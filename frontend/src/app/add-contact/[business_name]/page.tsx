"use client";

import { useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiClient } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export default function AddContactPage() {
  const { business_name } = useParams();
  const router = useRouter();
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [form, setForm] = useState({
    customer_name: "",
    phone: "",
    lifecycle_stage: "",
    pain_points: "",
    interaction_history: "",
  });

  const formatPhoneInput = (value: string) => {
    // Remove all non-digits first
    const digits = value.replace(/\D/g, '');
    
    // If user enters 10 digits, automatically add +1
    if (digits.length === 10) {
      return `+1${digits}`;
    }
    
    // If user is typing with country code, preserve the +
    if (value.startsWith('+')) {
      return `+${digits}`;
    }
    
    // For partial input, just return the digits
    return digits;
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    
    // Apply special formatting for phone field
    if (name === 'phone') {
      setForm(prev => ({
        ...prev,
        [name]: formatPhoneInput(value)
      }));
    } else {
      // Handle other fields normally
      setForm(prev => ({
        ...prev,
        [name]: value
      }));
    }
  };

  const handleSubmit = async () => {
    try {
      // Update the endpoint path to match the working ones
      const businessRes = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
      const { business_id } = businessRes.data;

      // Then create the customer
      const res = await apiClient.post("/customers", {
        ...form,
        business_id,
      });
      
      alert(
        "✅ Contact Added Successfully\n" +
        "──────────────────────\n" +
        "We've sent an opt-in request to your contact.\n" +
        "They'll need to reply 'YES' to receive messages.\n\n" +
        "Preview of their message:\n" +
        "──────────────────────\n" +
        `👋 Hi ${form.customer_name}! This is your therapist from BridgetoNowhere Therapy. ` +
        "I'd like to send you helpful updates and reminders.\n\n" +
        "Reply YES to opt in or STOP to opt out. Msg&data rates may apply."
      );
      
      console.log("✅ Contact added:", res.data);
      router.back();
    } catch (err) {
      console.error("❌ Failed to add contact:", err);
    }
  };

  return (
    <>
      <div className="max-w-xl mx-auto p-6 space-y-4">
        <h1 className="text-2xl font-bold">➕ Add New Contact</h1>
        <Input 
          name="customer_name" 
          placeholder="Full Name" 
          value={form.customer_name} 
          onChange={handleChange} 
        />
        <Input 
          name="phone" 
          placeholder="Phone Number (e.g. 3856268825)" 
          value={form.phone} 
          onChange={handleChange}
          maxLength={12} // +1 plus 10 digits
        />
        <Input 
          name="lifecycle_stage" 
          placeholder="Lifecycle Stage (e.g. Lead)" 
          value={form.lifecycle_stage} 
          onChange={handleChange} 
        />
        <Textarea 
          name="pain_points" 
          placeholder="Pain Points" 
          value={form.pain_points} 
          onChange={handleChange} 
        />
        <Textarea 
          name="interaction_history" 
          placeholder="Interaction History: Birthday, Holidays, Work Situation, # of Dogs, Frequency of SMS." 
          value={form.interaction_history} 
          onChange={handleChange} 
        />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => router.back()}>
            Cancel
          </Button>
          <Button onClick={handleSubmit}>
            Save Contact
          </Button>
        </div>
      </div>

      <Dialog open={showConfirmation} onOpenChange={setShowConfirmation}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              <div className="flex items-center gap-2">
                <span className="text-green-400 text-2xl">✅</span>
                <span>Contact Added Successfully</span>
              </div>
            </DialogTitle>
            <DialogDescription className="pt-4 space-y-4">
              <p>
                We've sent them a one-time opt-in request. You'll be able to message them after they reply 'YES'.
              </p>
              <div className="mt-4 p-4 rounded-lg bg-black/30 border border-white/10 space-y-2">
                <p className="text-sm font-medium text-white/60">Preview of the opt-in message:</p>
                <p className="text-white">
                  👋 Hi {form.customer_name}! This is your therapist from BridgetoNowhere Therapy. I'd like to send you helpful updates and reminders.
                </p>
                <p className="text-white">
                  Reply YES to opt in or STOP to opt out. Msg&data rates may apply.
                </p>
              </div>
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end mt-4">
            <Button onClick={() => {
              setShowConfirmation(false);
              router.back();
            }}>
              Done
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}