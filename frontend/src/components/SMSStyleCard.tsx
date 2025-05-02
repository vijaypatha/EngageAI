'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { apiClient } from '@/lib/api';

export function SMSStyleCard({ style, onUpdate, business_id }: {
  style: {
    id: number;
    scenario: string;
    response: string;
  };
  onUpdate: () => void;
  business_id: number;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [newResponse, setNewResponse] = useState(style.response);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      console.log("🔄 Saving SMS Style", newResponse);
      await apiClient.put(`/sms-style/scenarios/${business_id}/${style.id}`, newResponse);
      setIsEditing(false);
      onUpdate(); // refresh parent list
    } catch (error) {
      console.error("❌ Failed to save style update", error);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="p-4 shadow-sm rounded-2xl">
      <CardContent className="p-0 space-y-3">
        <div>
          <div className="text-xs text-muted-foreground mb-1">Scenario</div>
          <div className="font-medium text-sm">{style.scenario}</div>
        </div>

        <div>
          <div className="text-xs text-muted-foreground mb-1">Response</div>
          {isEditing ? (
            <textarea
                className="w-full rounded-md bg-white text-black border border-[#2A2F45] p-3 text-sm placeholder-gray-500 focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/50 transition-all duration-200"
              rows={4}
              value={newResponse}
              onChange={(e) => setNewResponse(e.target.value)}
            />
          ) : (
            <div className="text-sm whitespace-pre-wrap">{style.response}</div>
          )}
        </div>

        {isEditing ? (
          <div className="flex gap-2">
            <Button size="sm" onClick={handleSave} disabled={saving}>
              {saving ? 'Saving...' : 'Save'}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setNewResponse(style.response);
                setIsEditing(false);
              }}
            >
              Cancel
            </Button>
          </div>
        ) : (
          <div className="flex justify-end">
            <Button size="sm" 
          variant="ghost"
          onClick={() => setIsEditing(true)}
          className="px-6 py-2.5 bg-gradient-to-r from-emerald-400 to-blue-500 rounded-lg 
             text-white font-medium hover:opacity-90 transition-all duration-300 
             shadow-lg shadow-emerald-400/10"
          
          >
            Edit Response
          </Button>
          </div>
          
        )}
      </CardContent>
    </Card>
  );
}