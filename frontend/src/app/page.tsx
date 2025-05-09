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
      className={`min-h-screen w-full flex flex-col justify-start transition-opacity duration-1000 ${
        mounted ? "opacity-100" : "opacity-0"
      } bg-gradient-to-b from-black via-gray-900 to-gray-800`}
    >
      <div className="w-full px-4 sm:px-6 lg:px-12 py-20 space-y-16">
        {/* Hero Section */}
        <div className="text-center">
          <h1 className="text-5xl md:text-6xl font-extrabold mb-6 tracking-tight">
            Welcome to <span className="text-gradient">AI Nudge</span> 👋
          </h1>

          <p className="text-xl text-gray-300 mb-8 max-w-xl mx-auto leading-relaxed">
            Keep your clients close with timely, personal SMS nudges — in your style, on autopilot.
          </p>

          <h3 className="text-3xl md:text-4xl font-extrabold mb-6 mt-20 tracking-tight">
            <span className="text-gradient">How it works</span> 
          </h3>


          <p className="text-lg text-gray-300 mb-10 max-w-xl mx-auto leading-relaxed">
            🎯 Set goals → 🤝 Add contacts → 🤖 Create Nudge Plans <br />
            ✅ Review and Schedule → 🎉 Keep your clients close
          </p>

          <Link href="/onboarding" passHref>
            <div className="inline-block btn-primary mt-17 text-lg">
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
        </div>

        {/* Testimonials Section */}
        <div className="text-center">
          <h2 className="text-4xl font-bold mb-6">
            Small Businesses <span className="text-red-500">❤️</span> AI Nudge
          </h2>
          <p className="text-xl text-gray-300 mb-12 max-w-2xl mx-auto">
            From therapists to financial advisors, our users trust AI Nudge to keep client relationships strong and personal.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
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
                quote: "AI Nudge focuses on ALL my clients while I can only work with one or two clients in a day. That's real ROI."
              }
            ].map((person, i) => (
              <div key={i} className="card p-6 text-center group hover:scale-[1.02] transition-all duration-300">
                <img src={person.img} alt={person.name} className="w-24 h-24 rounded-full mx-auto mb-4 object-cover border-4 border-white/10" />
                <p className="font-semibold text-lg text-white">{person.name}</p>
                <p className="text-sm text-gray-400 mb-4">{person.title}</p>
                <p className="text-sm italic text-gray-300">"{person.quote}"</p>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <footer className="text-sm text-center space-y-6 border-t border-white/10 pt-12">
          <div className="space-y-2">
            <p className="font-semibold text-white text-base">AI Nudge</p>
            <p className="text-gray-400">Made with ❤️ in St. George, UT</p>
            <a href="mailto:support@ainudge.app" className="text-blue-400 hover:text-blue-300 underline">
              support@ainudge.app
            </a>
          </div>

          <div className="space-x-6 font-medium">
            <Link href="/terms" className="text-gray-400 hover:text-white underline">Terms of Service</Link>
            <Link href="/privacy" className="text-gray-400 hover:text-white underline">Privacy Policy</Link>
          </div>

          <div className="space-y-2 text-gray-500 text-sm max-w-2xl mx-auto">
            <p className="italic">Registered A2P 10DLC Messaging Provider (USA) · Fully compliant with carrier guidelines</p>
            <p className="italic">All messages include opt-out language · Reply STOP to unsubscribe. Standard message rates may apply. Message frequency varies.</p>
            <p className="text-xs mt-4">Message and data rates may apply. Carriers are not liable for delayed or undelivered messages.</p>
          </div>
        </footer>
      </div>
    </main>
  );
}