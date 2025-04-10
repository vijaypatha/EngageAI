"use client";

import { Button } from "@/components/ui/button";
import { useRouter } from "next/navigation"; 
import { useEffect } from "react";

export default function LandingPage() {
  const router = useRouter();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const businessName = params.get("business_name");
    if (businessName) {
      router.push(`/dashboard/${encodeURIComponent(businessName)}`);
    }
  }, []);

  return (
    <main className="min-h-screen bg-gradient-to-br from-zinc-950 via-zinc-900 to-neutral-900 text-white flex flex-col items-center justify-center px-6 py-12 font-sans">
      <h1 className="text-5xl sm:text-6xl font-extrabold text-center mb-6 tracking-tight leading-tight text-white">
        🚀 Welcome to EngageAI
      </h1>
      <p className="max-w-2xl text-lg sm:text-2xl text-center mb-14 leading-relaxed text-zinc-300 font-light">
        EngageAI helps business owners like{" "}
        <span className="font-semibold text-white">realtors, coaches, and insurance agents</span> connect with clients using{" "}
        <strong className="font-bold text-indigo-400">AI-powered, personalized SMS engagement plans</strong> — automatically scheduled and tracked for you.
      </p>

      {/* Features Grid */}
      <div className="grid sm:grid-cols-1 md:grid-cols-3 gap-6 mb-14 max-w-6xl w-full">
        {[
          {
            icon: "🤖",
            title: "Personalized SMS Plans",
            desc: "AI-generated messages tailored to your client’s needs, history, and tone.",
          },
          {
            icon: "📅",
            title: "Auto Scheduling",
            desc: "Set once. We send it at the perfect time using your business style.",
          },
          {
            icon: "📊",
            title: "Customer Intelligence",
            desc: "Turn notes into insights — track pain points, history, and engagement in one place.",
          },
        ].map((tile, idx) => (
          <div
            key={idx}
            className="bg-zinc-800 border border-zinc-700 p-6 rounded-2xl shadow-xl hover:scale-105 transition transform text-center text-white"
          >
            <div className="text-4xl mb-3">{tile.icon}</div>
            <h3 className="text-xl font-bold mb-2 text-indigo-300">{tile.title}</h3>
            <p className="text-sm text-zinc-300">{tile.desc}</p>
          </div>
        ))}
      </div>

      <Button
        className="bg-gradient-to-r from-blue-500 to-purple-500 hover:from-blue-600 hover:to-purple-600 text-white font-semibold transition duration-300 shadow-lg"
        onClick={async () => {
          const params = new URLSearchParams(window.location.search);
          const businessNameFromQuery = params.get("business_name");
          if (businessNameFromQuery) {
            router.push(`/dashboard/${encodeURIComponent(businessNameFromQuery)}`);
          } else {
            router.push("/add-business");
          }
        }}
      >
        Get Started →
      </Button>

    </main>
  );
}
