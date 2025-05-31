// frontend/src/components/FaqCard.tsx
"use client";

import { useState, useEffect, ChangeEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Trash2, Edit3, Save, XCircle, Loader2 } from 'lucide-react'; // Added Loader2 for consistency

export interface FaqItem {
  id: string;
  type: 'system' | 'custom';
  questionText: string;
  answerText: string;
  isEditing?: boolean;
  placeholder?: string;
}

interface FaqCardProps {
  item: FaqItem;
  onAnswerChange: (id: string, newAnswer: string) => void;
  onQuestionChange?: (id: string, newQuestion: string) => void;
  onRemove?: (id: string) => void;
  isSavingOverall?: boolean; // This prop signals if the PARENT form is submitting
  initialEditing?: boolean;
}

export function FaqCard({
  item,
  onAnswerChange,
  onQuestionChange,
  onRemove,
  isSavingOverall = false,
  initialEditing = false,
}: FaqCardProps) {
  const [isEditingThisCard, setIsEditingThisCard] = useState(
    initialEditing || item.isEditing || (item.type === "custom" && !item.questionText && !item.answerText)
  );
  // Local saving state for this specific card's save action
  const [isSavingThisCard, setIsSavingThisCard] = useState(false);

  const [currentAnswer, setCurrentAnswer] = useState(item.answerText);
  const [currentQuestion, setCurrentQuestion] = useState(item.questionText);

  useEffect(() => {
    setCurrentAnswer(item.answerText);
    setCurrentQuestion(item.questionText);
    // Reflect parent-driven editing state changes if item.isEditing is explicitly passed and changes
    if (item.isEditing !== undefined && item.isEditing !== isEditingThisCard) {
      setIsEditingThisCard(item.isEditing);
    }
  }, [item.answerText, item.questionText, item.isEditing]); // Removed isEditingThisCard from deps

  const handleSaveEdit = async () => {
    setIsSavingThisCard(true); // Indicate this card is attempting to save
    // Simulate async operation for visual feedback if needed, or directly call handlers
    // For actual async, you'd await promises here:
    // await new Promise(resolve => setTimeout(resolve, 500)); 

    if (item.type === "custom" && onQuestionChange) {
      onQuestionChange(item.id, currentQuestion.trim());
    }
    onAnswerChange(item.id, currentAnswer.trim());
    
    setIsEditingThisCard(false);
    setIsSavingThisCard(false); // Reset local saving state
  };

  const handleCancelEdit = () => {
    setCurrentAnswer(item.answerText);
    setCurrentQuestion(item.questionText);
    setIsEditingThisCard(false);
  };

  const isQuestionFieldActuallyEditable = item.type === 'custom' && onQuestionChange;
  const cardTitle = item.type === 'system' 
                    ? item.questionText 
                    : (currentQuestion || "New Q&A"); // Simplified placeholder for title

  // Disable all interactions if the parent form is submitting OR this specific card is saving
  const isDisabled = isSavingOverall || isSavingThisCard;

  return (
    <Card className="flex flex-col justify-between w-full rounded-xl border border-slate-700 bg-slate-800 shadow-lg hover:shadow-purple-500/20 transition-shadow duration-200 p-5">
      <CardHeader className="p-0 mb-3">
        {isEditingThisCard && isQuestionFieldActuallyEditable ? (
          <>
            <Label htmlFor={`faq-q-${item.id}`} className="text-xs text-slate-400 mb-1.5">
              Customer Asks:
            </Label>
            <Input
              id={`faq-q-${item.id}`}
              value={currentQuestion}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setCurrentQuestion(e.target.value)}
              disabled={isDisabled}
              placeholder="Enter the customer's question..."
              className="h-10 text-sm bg-slate-700 border-slate-600 text-slate-100 placeholder:text-slate-500 focus:ring-1 focus:ring-purple-500 focus:border-purple-500"
            />
          </>
        ) : (
          <CardTitle className="text-md font-semibold text-slate-100 tracking-tight leading-snug">
            {cardTitle}
          </CardTitle>
        )}
      </CardHeader>

      <CardContent className="p-0 text-sm flex-grow mb-4">
        {isEditingThisCard ? (
          <>
            <Label htmlFor={`faq-a-${item.id}`} className={`text-xs text-slate-400 mb-1.5 block ${isQuestionFieldActuallyEditable ? 'mt-3' : ''}`}>
              AI Nudge Should Answer:
            </Label>
            <Textarea
              id={`faq-a-${item.id}`}
              value={currentAnswer}
              onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setCurrentAnswer(e.target.value)}
              disabled={isDisabled}
              placeholder={item.placeholder || "Provide the answer AI should use..."}
              rows={4} // Increased rows for better editing space
              className="text-sm bg-slate-700 border-slate-600 text-slate-100 placeholder:text-slate-500 focus:ring-1 focus:ring-purple-500 focus:border-purple-500 scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-slate-700/50"
            />
          </>
        ) : (
          <div className="min-h-[60px] h-28 overflow-y-auto p-3 bg-slate-800/50 rounded-md scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-slate-800/80">
            <p
              className={`whitespace-pre-wrap ${
                currentAnswer ? "text-slate-300" : "italic text-slate-500"
              }`}
            >
              {currentAnswer || (item.type === 'custom' ? "No answer yet. Click 'Edit Answer' to add one." : "System-provided information will be used.")}
            </p>
          </div>
        )}
      </CardContent>

      <CardFooter className="p-0 flex justify-end gap-2 border-t border-slate-700/50 pt-4">
        {isEditingThisCard ? (
          <>
            <Button
              size="sm"
              variant="ghost"
              onClick={handleCancelEdit}
              disabled={isDisabled}
              className="text-slate-400 hover:text-slate-200 hover:bg-slate-700 px-3 py-1.5"
            >
              <XCircle className="w-4 h-4 mr-1.5" /> Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleSaveEdit}
              disabled={isDisabled || (!currentQuestion && item.type === 'custom') || !currentAnswer } // Basic validation
              className="bg-purple-600 hover:bg-purple-700 text-white px-3 py-1.5 flex items-center disabled:opacity-70"
            >
              {isSavingThisCard ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin"/> : <Save className="w-4 h-4 mr-1.5" />}
              Save
            </Button>
          </>
        ) : (
          <>
            {item.type === "custom" && onRemove && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => onRemove(item.id)}
                disabled={isDisabled}
                title="Remove Q&A"
                className="text-red-400 hover:text-red-300 hover:bg-red-700/30 p-2 disabled:opacity-70" 
              >
                <Trash2 className="w-4 h-4" /> 
                {/* <span className="ml-1.5 sm:hidden md:inline">Remove</span> */}
              </Button>
            )}
            <Button
              size="sm"
            //   variant="outline" // Using a purple-themed edit button
              onClick={() => setIsEditingThisCard(true)}
              disabled={isDisabled}
              title={currentAnswer ? "Edit Answer" : "Add Answer"}
              className="bg-blue-600/40 hover:bg-blue-500/60 text-blue-300 hover:text-blue-100 p-2 disabled:opacity-70"
            >
              <Edit3 className="w-4 h-4" />
              {/* <span className="ml-1.5 sm:hidden md:inline">{currentAnswer ? "Edit" : "Add"}</span> */}
            </Button>
          </>
        )}
      </CardFooter>
    </Card>
  );
}