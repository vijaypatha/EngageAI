// frontend/src/components/FaqCard.tsx
"use client";

import { useState, useEffect, ChangeEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Trash2, Edit3, Save, XCircle } from 'lucide-react';
import clsx from 'clsx';

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
  isSavingOverall?: boolean;
  className?: string;
}

export function FaqCard({
  item,
  onAnswerChange,
  onQuestionChange,
  onRemove,
  isSavingOverall = false,
  className,
}: FaqCardProps) {
  const [isEditingThisCard, setIsEditingThisCard] = useState(
    item.isEditing || (item.type === "custom" && !item.questionText && !item.answerText)
  );
  const [currentAnswer, setCurrentAnswer] = useState(item.answerText);
  const [currentQuestion, setCurrentQuestion] = useState(item.questionText);

  useEffect(() => {
    setCurrentAnswer(item.answerText);
    setCurrentQuestion(item.questionText);
    if (item.isEditing !== undefined && item.isEditing !== isEditingThisCard) {
      setIsEditingThisCard(item.isEditing);
    }
  }, [item.answerText, item.questionText, item.isEditing, isEditingThisCard]);

  const handleSaveEdit = () => {
    if (item.type === "custom" && onQuestionChange) {
      onQuestionChange(item.id, currentQuestion.trim());
    }
    onAnswerChange(item.id, currentAnswer.trim());
    // isEditingThisCard will be set to false via useEffect due to item.isEditing changing in parent
  };

  const handleCancelEdit = () => {
    setCurrentAnswer(item.answerText);
    setCurrentQuestion(item.questionText);
    setIsEditingThisCard(false); 
  };

  const isQuestionFieldActuallyEditable = item.type === 'custom' && onQuestionChange;
  const cardTitle = item.type === 'system' 
                    ? item.questionText 
                    : (currentQuestion || (isEditingThisCard ? "" : "New Q&A (Edit to define)"));

  // Define text color classes for dark background consistency
  const textPrimaryDarkBg = "text-slate-100"; // Brightest for titles/questions
  const textSecondaryDarkBg = "text-gray-300"; // For answers and important text
  const textMutedDarkBg = "text-gray-400"; // For labels and less important text
  const placeholderTextDarkBg = "text-gray-500 italic"; // For placeholders

  // Input and Textarea specific styling for dark theme
  const inputClassesDark = `bg-[#242842] border-[#333959] ${textPrimaryDarkBg} placeholder-gray-500 focus:border-emerald-500/70 focus:ring-1 focus:ring-emerald-500/70`;


  const baseCardClasses = "flex flex-col justify-between w-full transition-shadow duration-200";
  // Default theme classes from shadcn/ui (like border-border, bg-background) will be applied by <Card>
  // The `className` prop from parent will provide the specific dark background (e.g. bg-[#1A1D2D]) and border.

  return (
    <Card className={clsx(baseCardClasses, className)}> {/* className from props will apply bg, border etc. */}
      <CardHeader className="px-5 pt-4 pb-2">
        {isEditingThisCard && isQuestionFieldActuallyEditable ? (
          <>
            <Label htmlFor={`faq-q-${item.id}`} className={`text-xs ${textMutedDarkBg} mb-1`}>
              Customer Asks:
            </Label>
            <Input
              id={`faq-q-${item.id}`}
              value={currentQuestion}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setCurrentQuestion(e.target.value)}
              disabled={isSavingOverall}
              placeholder="Enter the customer's question..."
              className={`h-9 text-sm rounded-md ${inputClassesDark}`}
            />
          </>
        ) : (
          <CardTitle className={`text-base font-semibold ${textPrimaryDarkBg} tracking-tight leading-snug break-words`}>
            {cardTitle || item.questionText}
          </CardTitle>
        )}
      </CardHeader>

      <CardContent className="px-5 py-2 text-sm flex-grow">
        {isEditingThisCard ? (
          <>
            <Label htmlFor={`faq-a-${item.id}`} className={`text-xs ${textMutedDarkBg} mb-1 block mt-2`}>
              AI Nudge Should Answer:
            </Label>
            <Textarea
              id={`faq-a-${item.id}`}
              value={currentAnswer}
              onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setCurrentAnswer(e.target.value)}
              disabled={isSavingOverall}
              placeholder={item.placeholder || "Provide the answer AI should use..."}
              rows={4} // Adjusted rows for better editing space
              className={`text-sm rounded-md ${inputClassesDark}`}
            />
          </>
        ) : (
          <p
            className={`min-h-[40px] whitespace-pre-wrap break-words text-sm ${ // ensure text-sm for consistency
              item.answerText ? textSecondaryDarkBg : placeholderTextDarkBg
            }`}
          >
            {item.answerText || "No answer yet. Click Edit to add one."}
          </p>
        )}
      </CardContent>

      <CardFooter className="px-5 pb-4 pt-3 flex justify-end gap-2 border-t border-[#2A2F45]"> {/* Added explicit border color for footer top */}
        {isEditingThisCard ? (
          <>
            <Button
              size="sm"
              variant="ghost"
              onClick={handleCancelEdit}
              disabled={isSavingOverall}
              className={`${textMutedDarkBg} hover:bg-[#2A2F45]`}
            >
              <XCircle className="w-4 h-4 mr-1.5" /> Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleSaveEdit}
              disabled={isSavingOverall}
              className={`bg-emerald-500 text-white hover:bg-emerald-600`}
            >
              <Save className="w-4 h-4 mr-1.5" /> Save
            </Button>
          </>
        ) : (
          <div className="flex w-full justify-between items-center">
            {item.type === "custom" && onRemove ? (
              <Button
                size="icon"
                variant="ghost"
                onClick={() => onRemove(item.id)}
                disabled={isSavingOverall}
                className="text-red-500/70 hover:text-red-500 hover:bg-red-900/30 p-1.5 h-auto w-auto rounded"
                aria-label="Remove Q&A"
              >
                <Trash2 className="w-4 h-4" />
              </Button>
            ) : <div /> }
            <Button
              size="sm"
              variant="secondary" // This variant typically has a lighter bg or border in dark themes
              onClick={() => setIsEditingThisCard(true)}
              disabled={isSavingOverall}
              // Style the edit button for dark theme
              className={`bg-[#242842] hover:bg-[#333959] border border-[#333959] ${textSecondaryDarkBg} hover:${textPrimaryDarkBg}`}
            >
              <Edit3 className="w-4 h-4 mr-1.5" />
              {item.answerText ? "Edit" : "Add Answer"}
            </Button>
          </div>
        )}
      </CardFooter>
    </Card>
  );
}