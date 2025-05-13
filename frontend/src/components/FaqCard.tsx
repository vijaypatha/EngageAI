// frontend/src/components/FaqCard.tsx
"use client";

import { useState, useEffect, ChangeEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Trash2, Edit3, Save, XCircle } from 'lucide-react';

export interface FaqItem {
  id: string;
  type: 'system' | 'custom'; // Used by parent to know if question is editable & removable
  questionText: string;     // This will ALWAYS be the title
  answerText: string;
  isEditing?: boolean;       // For parent to suggest initial edit state
  placeholder?: string;
  // isPredefinedQuestion is effectively replaced by item.type === 'system' for parent's logic
}

interface FaqCardProps {
  item: FaqItem;
  onAnswerChange: (id: string, newAnswer: string) => void;
  onQuestionChange?: (id: string, newQuestion: string) => void; // Only for type: 'custom'
  onRemove?: (id: string) => void; // Only for type: 'custom'
  isSavingOverall?: boolean;
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
  const [currentAnswer, setCurrentAnswer] = useState(item.answerText);
  const [currentQuestion, setCurrentQuestion] = useState(item.questionText);

  useEffect(() => {
    setCurrentAnswer(item.answerText);
    setCurrentQuestion(item.questionText);
    if (item.isEditing !== undefined && item.isEditing !== isEditingThisCard) {
      setIsEditingThisCard(item.isEditing);
    }
  }, [item.answerText, item.questionText, item.isEditing]);

  const handleSaveEdit = () => {
    if (item.type === "custom" && onQuestionChange) {
      onQuestionChange(item.id, currentQuestion.trim());
    }
    onAnswerChange(item.id, currentAnswer.trim());
    setIsEditingThisCard(false);
  };

  const handleCancelEdit = () => {
    setCurrentAnswer(item.answerText);
    setCurrentQuestion(item.questionText);
    setIsEditingThisCard(false);
  };

  // Determine if the question field itself should be editable
  const isQuestionFieldActuallyEditable = item.type === 'custom' && onQuestionChange;

  // Determine the text to display as the card's title
  // For system cards, it's fixed. For custom, it's currentQuestion or a prompt if empty.
  const cardTitle = item.type === 'system' 
                    ? item.questionText 
                    : (currentQuestion || "New Q&A (Click Edit to define)");

  return (
    <Card className="flex flex-col justify-between w-full rounded-xl border border-border bg-background shadow-sm hover:shadow-md transition-shadow duration-200">
      <CardHeader className="px-5 pt-4 pb-2"> {/* Consistent padding */}
        {isEditingThisCard && isQuestionFieldActuallyEditable ? (
          // Editing the question of a CUSTOM FAQ
          <>
            <Label htmlFor={`faq-q-${item.id}`} className="text-xs text-muted-foreground mb-1">
              Customer Asks:
            </Label>
            <Input
              id={`faq-q-${item.id}`}
              value={currentQuestion}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setCurrentQuestion(e.target.value)}
              disabled={isSavingOverall}
              placeholder="Enter the customer's question..."
              className="h-9 text-sm" // Use consistent input styling
            />
          </>
        ) : (
          // Displaying the question as the title for ALL CARDS (system or custom)
          <CardTitle className="text-base font-semibold text-foreground tracking-tight leading-snug">
            {cardTitle}
          </CardTitle>
        )}
      </CardHeader>

      <CardContent className="px-5 py-2 text-sm flex-grow"> {/* flex-grow ensures content pushes footer down */}
        {isEditingThisCard ? (
          // Editing the answer
          <>
            <Label htmlFor={`faq-a-${item.id}`} className="text-xs text-muted-foreground mb-1 block mt-2"> {/* Added mt-2 if question also editable */}
              AI Nudge Should Answer:
            </Label>
            <Textarea
              id={`faq-a-${item.id}`}
              value={currentAnswer}
              onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setCurrentAnswer(e.target.value)}
              disabled={isSavingOverall}
              placeholder={item.placeholder || "Provide the answer AI should use..."}
              rows={3}
              className="text-sm" // Use consistent textarea styling
            />
          </>
        ) : (
          // Displaying the answer
          <p
            className={`min-h-[40px] whitespace-pre-wrap ${ // Ensure some min height
              currentAnswer ? "text-muted-foreground" : "italic text-muted-foreground/70"
            }`}
          >
            {currentAnswer || "No answer yet. Click Edit to add one."}
          </p>
        )}
      </CardContent>

      <CardFooter className="px-5 pb-4 pt-3 flex justify-end gap-2 border-t-0"> {/* Removed top border, adjusted padding */}
        {isEditingThisCard ? (
          <>
            <Button
              size="sm"
              variant="ghost"
              onClick={handleCancelEdit}
              disabled={isSavingOverall}
              className="text-muted-foreground"
            >
              <XCircle className="w-4 h-4 mr-1.5" /> Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleSaveEdit}
              disabled={isSavingOverall}
              className="bg-primary text-primary-foreground hover:bg-primary/90" // Assuming primary button style
            >
              <Save className="w-4 h-4 mr-1.5" /> Save
            </Button>
          </>
        ) : (
          <>
            {item.type === "custom" && onRemove && ( // Remove button only for custom FAQs
              <Button
                size="sm"
                variant="ghost"
                onClick={() => onRemove(item.id)}
                disabled={isSavingOverall}
                className="text-destructive hover:bg-destructive/10"
              >
                <Trash2 className="w-4 h-4 mr-1.5" /> Remove
              </Button>
            )}
            <Button
              size="sm"
              variant="secondary" // Or outline, depending on your theme
              onClick={() => setIsEditingThisCard(true)}
              disabled={isSavingOverall}
            >
              <Edit3 className="w-4 h-4 mr-1.5" />
              {currentAnswer ? "Edit Answer" : "Add Answer"}
            </Button>
          </>
        )}
      </CardFooter>
    </Card>
  );
}