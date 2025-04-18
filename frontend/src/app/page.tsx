"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

export default function LandingPage() {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <main
      className={`min-h-screen flex flex-col items-center justify-start pt-24 px-6 transition-opacity duration-1000 ${mounted ? "opacity-100" : "opacity-0"
        } bg-gradient-to-b from-black via-gray-900 to-gray-800 text-white`}
    >
      <h1 className="text-5xl md:text-6xl font-extrabold mb-6 text-center tracking-tight">
        Welcome to <span className="text-green-400">AI Nudge 👋</span>
      </h1>

      <p className="text-xl text-gray-300 mb-10 text-center max-w-2xl leading-relaxed">
        AI Nudge is a trusted communication platform that helps service-based businesses follow up with clients through thoughtful SMS conversations. Whether it's a check-in after a session, a gentle reminder, or a thank-you message — we help real businesses stay human at scale.
      </p>

      <Link href="/onboarding" passHref>
        <div className="px-8 py-4 bg-gradient-to-r from-green-400 to-blue-500 hover:from-green-500 hover:to-blue-600 text-white rounded-lg text-lg font-medium shadow-lg transition transform hover:scale-105 cursor-pointer">
          🚀 Try It Free — No Login Needed
        </div>
      </Link>

      <p className="mt-6 text-gray-400 text-sm">
        Already using AI Nudge?{" "}
        <Link href="/auth/login" passHref>
          <span className="underline text-blue-400 hover:text-blue-300 cursor-pointer">
            Log in here
          </span>
        </Link>
      </p>

      <section className="mt-20 w-full max-w-7xl px-6 text-center">
        <h2 className="text-4xl font-extrabold text-white mb-4">Small Businesses & Professionals ❤️ AI Nudge</h2>
        <p className="text-lg text-gray-300 mb-12 max-w-2xl mx-auto">From therapists to financial advisors, our users trust AI Nudge to keep client relationships strong and personal.</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8">
          {[
            {
              name: "Dr. Eliza Stone",
              title: "CareBridge Therapy",
              img: "https://images.unsplash.com/photo-1517841905240-472988babdf9?auto=format&fit=crop&w=300&h=300&q=80",
              quote: "AI Nudge lets me stay in touch with clients in a way that feels authentic."
            },
            {
              name: "Marcus Bell",
              title: "Bell Financial",
              img: "https://images.unsplash.com/photo-1552058544-f2b08422138a?auto=format&fit=crop&w=300&h=300&q=80",
              quote: "The reminders and check-ins look like I wrote them myself — it builds trust."
            },
            {
              name: "Sofia Tran",
              title: "Red Rose Yoga",
              img: "https://images.unsplash.com/photo-1607746882042-944635dfe10e?auto=format&fit=crop&w=300&h=300&q=80",
              quote: "I can focus on care — AI Nudge follows up with kindness and clarity."
            },
            {
              name: "Reggie Scott",
              title: "Scott Realty",
              img: "https://images.unsplash.com/photo-1573497491208-6b1acb260507?auto=format&fit=crop&w=300&h=300&q=80",
              quote: "Clients message back like I sent it personally. That's real ROI."
            }
          ].map((person, i) => (
            <div key={i} className="bg-gradient-to-br from-gray-800 to-gray-700 rounded-2xl p-6 text-white hover:shadow-xl transition group relative flex flex-col items-center">
              <img src={person.img} alt={person.name} className="rounded-full w-24 h-24 object-cover mb-4 border-4 border-white shadow-md" />
              <p className="font-semibold text-lg">{person.name}</p>
              <p className="text-sm text-gray-300 mb-3">{person.title}</p>
              <p className="text-sm italic text-gray-200">“{person.quote}”</p>
            </div>
          ))}
        </div>
      </section>

      
      <footer className="mt-24 text-sm text-gray-400 text-center space-y-4 border-t border-gray-700 pt-10">
        <div className="space-y-1">
          <p className="font-semibold text-white text-base">AI Nudge</p>
          <p className="text-gray-400"> Based in St. Geroge, UT</p>
          <p>
            <a href="mailto:support@ainudge.app" className="underline hover:text-gray-200">
              support@ainudge.app
            </a>
          </p>
        </div>
        <div className="space-x-6 font-medium">
          <Link href="/terms" className="underline hover:text-gray-200">Terms of Service</Link>
          <Link href="/privacy" className="underline hover:text-gray-200">Privacy Policy</Link>
        </div>
        <div className="text-gray-500 italic">
          Registered A2P 10DLC Messaging Provider (USA) · Fully compliant with carrier guidelines
        </div>
        <div className="text-gray-500 italic">
          All messages include opt-out language · “Reply STOP to unsubscribe. Standard message rates may apply.”
        </div>
      </footer>
    </main>
  );
}