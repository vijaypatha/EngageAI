// /train-style/page.tsx — AI SMS Style Training Page

"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export default function TrainStylePage() {
  const router = useRouter();
  const [questions, setQuestions] = useState<string[]>([]);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const businessId = localStorage.getItem("business_id");
    if (!businessId) return;

    apiClient.get(`/sms-style/scenarios/${businessId}`).then((res) => {
      setQuestions(res.data.scenarios || []);
      setLoading(false);
    });
  }, []);

  const handleSubmit = async () => {
    const businessId = localStorage.getItem("business_id");
    if (!businessId) return;

    const payload = questions.map((scenario, i) => ({
      scenario,
      response: answers[i] || "",
      business_id: Number(businessId),
    }));

    try {
      await apiClient.post("/sms-style", payload);
      router.push("/add-customer");
    } catch (err) {
      alert("Failed to submit style responses.");
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-zinc-950 via-zinc-900 to-neutral-900 text-white p-8 pb-32">
      <h1 className="text-4xl font-bold mb-4">✍️ Train EngageAI Your SMS Style</h1>
      <p className="text-zinc-400 text-sm mb-10">Respond naturally to common scenarios so we can mirror your voice.</p>

      {loading ? (
        <p className="text-zinc-400 animate-pulse">Loading questions...</p>
      ) : (
        <div className="space-y-10 max-w-2xl">
          {questions.map((q, i) => (
            <div key={i}>
              <p className="font-semibold text-zinc-300 mb-2">{q}</p>
              <Textarea
                className="bg-zinc-900 border-zinc-700 text-white"
                placeholder="Your natural response..."
                value={answers[i] || ""}
                onChange={(e) => setAnswers((prev) => ({ ...prev, [i]: e.target.value }))}
              />
            </div>
          ))}

          <Button
            className="bg-black text-white border border-zinc-600 hover:bg-zinc-900 hover:border-zinc-500 transition"
            onClick={handleSubmit}
          >
            🚀 Save & Continue
          </Button>
        </div>
      )}
    </div>
  );
}
