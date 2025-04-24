"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiClient } from "@/lib/api";
import { US_TIMEZONES, TIMEZONE_LABELS } from "@/lib/timezone";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface BusinessProfile {
  business_name: string;
  representative_name: string;
}

interface FormData {
  customer_name: string;
  phone: string;
  lifecycle_stage: string;
  pain_points: string;
  interaction_history: string;
  timezone: string;
}

export default function AddContactPage() {
  const { business_name } = useParams();
  const router = useRouter();
  const [businessProfile, setBusinessProfile] = useState<BusinessProfile | null>(null);
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [form, setForm] = useState<FormData>({
    customer_name: "",
    phone: "",
    lifecycle_stage: "",
    pain_points: "",
    interaction_history: "",
    timezone: "America/New_York",
  });

  // Fetch business profile when component mounts
  useEffect(() => {
    const fetchBusinessProfile = async () => {
      try {
        const idRes = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
        const { business_id } = idRes.data;
        
        const profileRes = await apiClient.get(`/business-profile/${business_id}`);
        setBusinessProfile(profileRes.data);
      } catch (err) {
        console.error("Failed to fetch business profile:", err);
      }
    };

    fetchBusinessProfile();
  }, [business_name]);

  const formatPhoneInput = (value: string) => {
    const digits = value.replace(/\D/g, '');
    if (digits.length === 10) return `+1${digits}`;
    if (value.startsWith('+')) return `+${digits}`;
    return digits;
  };

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => {
    if (e.target.name === "phone") {
      setForm((prev) => ({
        ...prev,
        [e.target.name]: formatPhoneInput(e.target.value),
      }));
    } else {
      setForm((prev) => ({
        ...prev,
        [e.target.name]: e.target.value,
      }));
    }
  };

  const handleSubmit = async () => {
    try {
      const businessRes = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
      const { business_id } = businessRes.data;

      await apiClient.post("/customers", {
        ...form,
        business_id,
      });
      
      router.back();
    } catch (err) {
      console.error("❌ Failed to add contact:", err);
    }
  };

  return (
    <div className="flex min-h-screen bg-[#0C0F1F] items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
      <div className="w-full max-w-2xl rounded-xl border border-white/10 bg-gradient-to-b from-[#0C0F1F] to-[#111629] shadow-2xl p-8 space-y-6">
        <h1 className="text-3xl font-bold text-center text-white">➕ Add New Contact</h1>
        <div className="space-y-6">
          <Input 
            name="customer_name" 
            placeholder="Full Name" 
            value={form.customer_name} 
            onChange={handleChange}
            className="bg-white text-black" 
          />
          <Input 
            name="phone" 
            placeholder="Phone Number (e.g. 3856268825)" 
            value={form.phone} 
            onChange={handleChange}
            maxLength={12}
            className="bg-white text-black" 
          />
          <Input 
            name="lifecycle_stage" 
            placeholder="Lifecycle Stage (e.g. Lead)" 
            value={form.lifecycle_stage} 
            onChange={handleChange}
            className="bg-white text-black" 
          />
          <div className="space-y-2">
            <label className="block text-sm font-medium text-white">
              Customer's Timezone
            </label>
            <select
              name="timezone"
              value={form.timezone}
              onChange={handleChange}
              className="w-full border border-gray-300 rounded-md p-3 text-black bg-white"
            >
              {US_TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>
                  {TIMEZONE_LABELS[tz]}
                </option>
              ))}
            </select>
            <p className="text-sm text-gray-400">
              This helps us send messages at appropriate times for your customer
            </p>
          </div>
          <Textarea 
            name="pain_points" 
            placeholder="Pain Points" 
            value={form.pain_points} 
            onChange={handleChange}
            className="bg-white text-black" 
          />
          <Textarea 
            name="interaction_history" 
            placeholder="Interaction History: Birthday, Holidays, Work Situation, # of Dogs, Frequency of SMS." 
            value={form.interaction_history} 
            onChange={handleChange}
            className="bg-white text-black" 
          />

          {/* Opt-in Message Preview */}
          <div className="mt-8 p-4 rounded-lg bg-black/30 border border-white/10 space-y-3">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-blue-400 text-xl">📱</span>
              <h3 className="text-white font-medium">Opt-in Message Preview</h3>
            </div>
            <p className="text-sm text-white/70">
              When you save this contact, we'll send them this message:
            </p>
            <div className="bg-[#1A1D2D] p-4 rounded-md border border-white/5 space-y-2">
              <p className="text-white">
                👋 Hi {form.customer_name || "[name]"}! This is {businessProfile?.representative_name || "[representative]"} from {businessProfile?.business_name || "..."}. 
                I'd like to send you helpful updates and reminders.
              </p>
              <p className="text-white/80 text-sm">
                Reply YES to opt in or STOP to opt out. Msg&data rates may apply.
              </p>
            </div>
          </div>

          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => router.back()} className="text-white">
              Cancel
            </Button>
            <Button 
              onClick={handleSubmit} 
              className="bg-gradient-to-r from-green-400 to-blue-500 text-white"
              disabled={!form.customer_name || !form.phone || !form.lifecycle_stage}
            >
              Save Contact
            </Button>
          </div>
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
                  👋 Hi {form.customer_name}! This is {businessProfile?.representative_name || "[representative]"} from {businessProfile?.business_name || "..."}. I'd like to send you helpful updates and reminders.
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
    </div>
  );
}