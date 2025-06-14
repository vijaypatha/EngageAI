// frontend/src/components/FaqCard.tsx
"use client";

import { useState, useEffect, ChangeEvent } from 'react';
import { Input } from './ui/input';
import { Textarea } from './ui/textarea';
import { Label } from './ui/label';
import { Trash2, Edit3, Save, XCircle, Loader2 } from 'lucide-react';

export interface FaqItem {
  id: string;
  type: 'system' | 'custom';
  questionText: string;
  answerText: string;
  isEditing?: boolean;
}

interface FaqCardProps {
  item: FaqItem;
  onAnswerChange: (id: string, newAnswer: string) => void;
  onQuestionChange?: (id: string, newQuestion: string) => void;
  onRemove?: (id: string) => void;
  isSavingOverall?: boolean; // This prop signals if the PARENT form is submitting
}

export function FaqCard({
  item,
  onAnswerChange,
  onQuestionChange,
  onRemove,
  isSavingOverall = false,
}: FaqCardProps) {
  const [isEditing, setIsEditing] = useState(
    item.isEditing || (item.type === "custom" && !item.questionText && !item.answerText)
  );
  const [currentAnswer, setCurrentAnswer] = useState(item.answerText);
  const [currentQuestion, setCurrentQuestion] = useState(item.questionText);

  // Effect to sync state with props from parent
  useEffect(() => {
    setCurrentAnswer(item.answerText);
    setCurrentQuestion(item.questionText);
  }, [item.answerText, item.questionText]);

  const handleSave = () => {
    if (item.type === "custom" && onQuestionChange) {
      onQuestionChange(item.id, currentQuestion.trim());
    }
    onAnswerChange(item.id, currentAnswer.trim());
    setIsEditing(false);
  };

  const handleCancel = () => {
    setCurrentAnswer(item.answerText);
    setCurrentQuestion(item.questionText);
    setIsEditing(false);
  };
  
  const isQuestionEditable = item.type === 'custom' && onQuestionChange;

  return (
    <div className="flex flex-col w-full rounded-xl border border-slate-700 bg-slate-800 shadow-lg p-5 min-h-[250px] justify-between">
        {/* Card Header & Content Area */}
        <div className="flex-grow">
            {isEditing && isQuestionEditable ? (
                <div className="mb-3">
                    <Label htmlFor={`q-${item.id}`} className="text-xs font-semibold text-slate-400">Question</Label>
                    <Input
                        id={`q-${item.id}`}
                        value={currentQuestion}
                        onChange={(e) => setCurrentQuestion(e.target.value)}
                        disabled={isSavingOverall}
                        placeholder="Enter customer question"
                        className="mt-1 bg-slate-700 border-slate-600 text-white"
                    />
                </div>
            ) : (
                <h3 className="font-bold text-white mb-2">{item.questionText}</h3>
            )}
            
            {isEditing ? (
                <div>
                    <Label htmlFor={`a-${item.id}`} className="text-xs font-semibold text-slate-400">Answer</Label>
                    <Textarea
                        id={`a-${item.id}`}
                        value={currentAnswer}
                        onChange={(e) => setCurrentAnswer(e.target.value)}
                        disabled={isSavingOverall}
                        placeholder="Enter the auto-reply answer"
                        rows={5}
                        className="mt-1 bg-slate-700 border-slate-600 text-white"
                    />
                </div>
            ) : (
                <p className={`text-sm text-slate-300 whitespace-pre-wrap ${!currentAnswer && 'italic text-slate-500'}`}>
                    {currentAnswer || "No answer provided."}
                </p>
            )}
        </div>
        
        {/* Card Footer Area */}
        <div className="flex justify-end gap-2 border-t border-slate-700/50 pt-4 mt-4">
            {isEditing ? (
                <>
                    <button onClick={handleCancel} disabled={isSavingOverall} className="px-3 py-1.5 text-sm rounded-md flex items-center gap-1.5 text-slate-300 hover:bg-slate-700">
                        <XCircle size={14} /> Cancel
                    </button>
                    <button onClick={handleSave} disabled={isSavingOverall} className="px-3 py-1.5 text-sm rounded-md flex items-center gap-1.5 bg-purple-600 hover:bg-purple-700 text-white">
                        <Save size={14} /> Save
                    </button>
                </>
            ) : (
                <>
                    {item.type === "custom" && onRemove && (
                        <button onClick={() => onRemove(item.id)} disabled={isSavingOverall} className="p-2 text-red-400 hover:bg-red-900/50 rounded-md">
                            <Trash2 size={16} />
                        </button>
                    )}
                    <button onClick={() => setIsEditing(true)} disabled={isSavingOverall} className="p-2 text-blue-300 hover:bg-blue-900/50 rounded-md">
                        <Edit3 size={16} />
                    </button>
                </>
            )}
        </div>
    </div>
  );
}