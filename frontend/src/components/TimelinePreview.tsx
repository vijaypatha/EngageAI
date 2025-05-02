// components/TimelinePreview.tsx
'use client';

import React, { useState } from 'react';
import { format } from 'date-fns';
import { groupBy } from 'lodash-es';
import { Button } from '@/components/ui/button';
import axios from 'axios';

interface Message {
  id: number;
  message: string;
  send_datetime: string;
  status: string;
  timezone?: string;
}

interface TimelinePreviewProps {
  messages: Message[];
  customerId: number;
  businessId: number;
  timezone?: string;
  onRefresh: () => void;
}

export default function TimelinePreview({ messages, customerId, businessId, timezone = 'America/Denver', onRefresh }: TimelinePreviewProps) {
  const [editingMessageId, setEditingMessageId] = useState<number | null>(null);
  const [editedContent, setEditedContent] = useState<string>('');
  const [editedTime, setEditedTime] = useState<string>('');

  const grouped = groupBy(messages, (m) => format(new Date(m.send_datetime), 'MMM yyyy'));

  const handleEdit = async (id: number, updated: Partial<Message>) => {
    try {
      await axios.put(`/roadmap-workflow/update-time/${id}`, updated);
      onRefresh();
    } catch (err) {
      console.error('Failed to update message', err);
    }
  };

  const handleSaveEdit = async (id: number) => {
    try {
      const iso = new Date(editedTime).toISOString();
      await handleEdit(id, { message: editedContent, send_datetime: iso });
      setEditingMessageId(null);
    } catch (err) {
      console.error('Failed to save edit', err);
    }
  };

  const handleRegenerate = async () => {
    try {
      await axios.post(`/ai_sms/roadmap`, {
        business_id: businessId,
        customer_id: customerId,
        force_regenerate: true,
      });
      onRefresh();
    } catch (err) {
      console.error('Failed to regenerate roadmap', err);
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-yellow-100 text-yellow-800 p-4 rounded-md text-sm">
        ⚠️ These messages won't be sent until your Nudge Number is activated.
      </div>

      <div className="text-right">
        <Button variant="ghost" onClick={handleRegenerate}>
          🔄 Regenerate
        </Button>
      </div>

      {Object.entries(grouped).map(([month, msgs]) => (
        <div key={month}>
          <h2 className="text-xl font-semibold text-white border-b border-white/20 mb-4 mt-12">{month}</h2>
          <div className="relative border-l-4 border-purple-500 ml-8">
            {msgs.map((msg) => {
              const date = new Date(msg.send_datetime);
              return (
                <div key={msg.id} className="relative mb-12 pl-10 mt-12">
                  <div className="absolute -left-6 top-1/2 transform -translate-y-1/2 flex flex-col items-center gap-1">
                    <div className="w-12 h-12 rounded-full bg-gradient-to-br from-purple-600 to-pink-500 flex flex-col items-center justify-center text-white font-bold text-xs shadow-md">
                      <span>{format(date, 'LLL').toUpperCase()}</span>
                      <span className="text-lg">{format(date, 'd')}</span>
                    </div>
                    <div className="w-px flex-1 bg-purple-500 mt-2"></div>
                  </div>
                  <div className="ml-4 rounded-lg shadow-md p-4 bg-zinc-800 border border-neutral text-white">
                    <div className="flex justify-between items-center mb-1">
                      <div className="text-lg mb-2">
                        {format(date, 'EEEE')}, {format(date, 'h:mm a')} ({timezone.split('/')[1].replace('_', ' ')})
                      </div>
                      <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-sm tracking-wide bg-yellow-600 text-white">
                        scheduled
                      </span>
                    </div>
                    {editingMessageId === msg.id ? (
                      <>
                        <textarea
                          value={editedContent}
                          onChange={(e) => setEditedContent(e.target.value)}
                          className="w-full p-2 text-sm text-white bg-zinc-800 border border-neutral rounded mb-2"
                          rows={3}
                        />
                        <input
                          type="datetime-local"
                          value={editedTime}
                          onChange={(e) => setEditedTime(e.target.value)}
                          className="w-full p-2 text-sm text-white bg-zinc-800 border border-neutral rounded mb-4"
                        />
                        <div className="flex justify-end gap-2">
                          <button onClick={() => setEditingMessageId(null)} className="text-sm px-3 py-1 bg-gray-500 hover:bg-gray-600 rounded text-white shadow">
                            Cancel
                          </button>
                          <button onClick={() => handleSaveEdit(msg.id)} className="text-sm px-3 py-1 bg-primary hover:bg-primary/80 rounded text-white shadow">
                            Save
                          </button>
                        </div>
                      </>
                    ) : (
                      <>
                        <p className="text-white text-sm leading-relaxed mb-4">{msg.message}</p>
                        <div className="flex justify-end gap-2">
                          <button
                            onClick={() => {
                              setEditingMessageId(msg.id);
                              setEditedContent(msg.message);
                              setEditedTime(msg.send_datetime);
                            }}
                            className="text-sm px-3 py-1 bg-blue-600 hover:bg-blue-700 rounded text-white shadow"
                          >
                            🪄 Edit
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}