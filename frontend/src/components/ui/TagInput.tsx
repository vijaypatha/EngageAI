// frontend/src/components/ui/TagInput.tsx
// CORRECTED VERSION 4 - Addresses Button variant error, keeps modal debugging logs

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { X, Trash2, Loader2, Settings, AlertTriangle } from 'lucide-react';
import { Tag } from '../../types'; // Ensure this path is correct
import { getBusinessTags, createBusinessTag, deleteTagPermanently } from '../../lib/api'; // Ensure this path is correct
import { Input } from './input';   // Ensure this path is correct
import { Button } from './button'; // Ensure this path is correct
import { cn } from '../../lib/utils';   // Ensure this path is correct
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter
} from "@/components/ui/dialog"; // Ensure this path is correct
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger
} from "@/components/ui/alert-dialog"; // Ensure this path is correct


interface TagInputProps {
  businessId: number;
  initialTags: Tag[];
  onChange: (updatedTags: Tag[]) => void;
  className?: string;
}

export const TagInput: React.FC<TagInputProps> = ({
  businessId,
  initialTags,
  onChange,
  className,
}) => {
  const [inputValue, setInputValue] = useState('');
  const [selectedTags, setSelectedTags] = useState<Tag[]>(initialTags);
  const [availableTags, setAvailableTags] = useState<Tag[]>([]);
  const [filteredOptions, setFilteredOptions] = useState<Tag[]>([]);
  const [isActionLoading, setIsActionLoading] = useState(false);
  const [isFetchingTags, setIsFetchingTags] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [showManageSection, setShowManageSection] = useState(false); // State for inline section
  const [manageError, setManageError] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const containerClassName = 'tag-input-container';

  const fetchTags = useCallback(async (triggeredByModal = false) => {
    if (!businessId) return;
    console.log(`[TagInput] Fetching tags (triggeredByModal: ${triggeredByModal}) for business:`, businessId);
    setIsFetchingTags(true);
    if (triggeredByModal) setManageError(null);
    try {
      const tags = await getBusinessTags(businessId);
      console.log('[TagInput] Fetched tags result:', tags);
      setAvailableTags(tags);
    } catch (error: any) {
      console.error("[TagInput] Failed to fetch tags:", error);
      if (triggeredByModal) setManageError("Could not load tags.");
    } finally {
      setIsFetchingTags(false);
    }
  }, [businessId]);

  useEffect(() => { fetchTags(); }, [fetchTags]);
  useEffect(() => { setSelectedTags(initialTags); }, [initialTags]);
  useEffect(() => { onChange(selectedTags); }, [selectedTags, onChange]);
  useEffect(() => {
    const lowerInputValue = inputValue.toLowerCase().trim();
    if (lowerInputValue && showDropdown) { const available = availableTags.filter(t => t.name.toLowerCase().includes(lowerInputValue) && !selectedTags.some(st => st.id === t.id)); setFilteredOptions(available); } else { setFilteredOptions([]); }
  }, [inputValue, availableTags, selectedTags, showDropdown]);
   useEffect(() => {
       const handleClickOutside = (event: MouseEvent) => { const container = inputRef.current?.closest(`.${containerClassName}`); if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node) && container && !container.contains(event.target as Node)) { setShowDropdown(false); } };
       document.addEventListener('mousedown', handleClickOutside); return () => document.removeEventListener('mousedown', handleClickOutside);
   }, []);

  const handleAddTag = useCallback((tag: Tag) => { if (!selectedTags.some(st => st.id === tag.id)) setSelectedTags(prev => [...prev, tag]); setInputValue(''); setFilteredOptions([]); setShowDropdown(false); inputRef.current?.focus(); }, [selectedTags]);
  const handleRemoveTag = (tagId: number) => { setSelectedTags(prev => prev.filter(t => t.id !== tagId)); };
  const handleCreateTag = async () => {
      const newTagName = inputValue.trim(); if (!newTagName || isActionLoading) return; const existing = availableTags.find(t => t.name.toLowerCase() === newTagName.toLowerCase()); if (existing) { if (!selectedTags.some(st => st.id === existing.id)) handleAddTag(existing); else { setInputValue(''); setShowDropdown(false); } return; }
      setIsActionLoading(true); setManageError(null);
      try { const created = await createBusinessTag(businessId, newTagName); setAvailableTags(prev => [...prev, created].sort((a, b) => a.name.localeCompare(b.name))); handleAddTag(created); }
      catch (err: any) { console.error("Create tag failed:", err); setManageError(err?.response?.data?.detail || "Failed to create tag."); }
      finally { setIsActionLoading(false); }
  };

  const handleDeleteTag = async (tagToDelete: Tag) => {
    if (!tagToDelete || isActionLoading) return;
    if (!window.confirm(`Permanently delete tag "${tagToDelete.name}"? This removes it from all contacts.`)) return;
    setIsActionLoading(true); setManageError(null);
    try {
      await deleteTagPermanently(tagToDelete.id);
      setAvailableTags(prev => prev.filter(t => t.id !== tagToDelete.id));
      setSelectedTags(prev => prev.filter(t => t.id !== tagToDelete.id));
    } catch (err: any) { console.error("Failed to delete tag:", err); setManageError(err?.response?.data?.detail || "Could not delete tag."); }
    finally { setIsActionLoading(false); }
  };

  const toggleManageSection = () => {
      console.log('[TagInput] Toggling manage section. Current showManageSection:', showManageSection);
      setShowManageSection(prev => !prev);
      setShowDropdown(false);
      // If opening the manage section and tags haven't been fetched or are stale, fetch them.
      if (!showManageSection && (!availableTags.length || isFetchingTags)) {
        fetchTags(true); // Pass true to indicate it's for the modal/section
      }
  };

  const canCreate = inputValue.trim().length > 0;
  const showCreateOption = canCreate && !availableTags.some(t => t.name.toLowerCase() === inputValue.trim().toLowerCase());
  const showEmptyMessage = showDropdown && inputValue && filteredOptions.length === 0 && !showCreateOption && !isActionLoading && !isFetchingTags;
  const showSeparator = showDropdown && (filteredOptions.length > 0 || showCreateOption);

  console.log('[TagInput] Render. showManageSection:', showManageSection, 'isFetchingTags:', isFetchingTags, 'availableTags:', availableTags.length);

  return (
    <div className={cn("w-full", className)}>
      <div className={cn("relative w-full", containerClassName)}>
        <div className={cn("flex flex-wrap gap-1 items-center p-2 border border-input rounded-md bg-background min-h-[40px] cursor-text")} onClick={() => inputRef.current?.focus()}>
            {selectedTags.map((tag) => ( <span key={tag.id} className="flex items-center gap-1 bg-secondary text-secondary-foreground text-xs font-medium px-2 py-0.5 rounded-full whitespace-nowrap"> {tag.name} <button type="button" onClick={(e) => { e.stopPropagation(); handleRemoveTag(tag.id); }} className="ml-1 text-muted-foreground hover:text-foreground rounded-full hover:bg-muted p-0.5" aria-label={`Remove tag ${tag.name}`}> <X size={12} strokeWidth={3} /> </button> </span> ))}
            <Input ref={inputRef} type="text" value={inputValue} onChange={(e) => setInputValue(e.target.value)} onFocus={() => setShowDropdown(true)} placeholder={selectedTags.length === 0 ? "Add or find tags..." : ""} className="flex-grow border-none outline-none focus-visible:ring-0 focus-visible:ring-offset-0 shadow-none p-0 h-5 bg-transparent min-w-[80px]" onKeyDown={(e) => { if (e.key === 'Enter' && showCreateOption && inputValue.trim()){ e.preventDefault(); handleCreateTag();} if (e.key === 'Backspace' && inputValue === '' && selectedTags.length > 0){ e.preventDefault(); handleRemoveTag(selectedTags[selectedTags.length - 1].id);} if (e.key === 'Escape'){ setShowDropdown(false);}}} disabled={isActionLoading || isFetchingTags}/>
        </div>

        {showDropdown && (
          <div ref={dropdownRef} className="absolute z-10 w-full mt-1 bg-popover border border-border rounded-md shadow-lg max-h-60 overflow-y-auto text-popover-foreground">
            <ul className="p-1">
                 {filteredOptions.map((tag) => ( <li key={tag.id} className="flex justify-between items-center px-2 py-1.5 text-sm hover:bg-accent rounded-[2px] cursor-pointer" onMouseDown={(e) => { e.preventDefault(); handleAddTag(tag); }}> <span>{tag.name}</span> </li> ))}
                 {showCreateOption && ( <li className="px-2 py-1.5 text-sm text-muted-foreground hover:bg-accent rounded-[2px] cursor-pointer font-medium" onMouseDown={(e) => { e.preventDefault(); handleCreateTag(); }}> + Create tag: "{inputValue.trim()}" </li> )}
                 {showEmptyMessage && ( <li className="px-2 py-1.5 text-sm text-muted-foreground italic">No matching tags found.</li> )}
                 {showSeparator && ( <hr className="my-1 border-border" /> )}
                 <li className="px-2 py-1.5 text-sm text-muted-foreground hover:bg-accent rounded-[2px] cursor-pointer flex items-center gap-2" onMouseDown={(e) => { e.preventDefault(); toggleManageSection(); }}> <Settings size={14} /> {showManageSection ? 'Hide' : 'Manage all'} tags... </li>
            </ul>
             {(isActionLoading || isFetchingTags) && ( <div className="flex items-center justify-center p-2"><Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /></div>)}
          </div>
        )}
      </div>

      {showManageSection && (
        <div className="mt-4 p-4 border border-border rounded-md bg-card">
          <h4 className="text-md font-semibold mb-3 text-card-foreground">Manage All Tags</h4>
          <div className="max-h-[40vh] overflow-y-auto min-h-[100px]">
            {isFetchingTags ? ( <div className="flex items-center justify-center p-4"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /> Loading Tags...</div>
            ) : manageError ? ( <p className="text-sm text-destructive text-center py-4">{manageError}</p>
            ) : availableTags.length === 0 ? ( <p className="text-sm text-muted-foreground text-center py-4">No tags created yet.</p>
            ) : (
              <ul className="space-y-1 pr-2">
                {availableTags.map((tag) => (
                  <li key={tag.id} className="flex justify-between items-center p-2 rounded hover:bg-accent/50">
                    <span className="text-sm text-card-foreground flex-1 mr-2 break-all">{tag.name}</span>
                    <Button type="button" variant="ghost" size="icon" className="h-7 w-7 text-destructive hover:text-destructive hover:bg-destructive/10 flex-shrink-0" onClick={() => handleDeleteTag(tag)} disabled={isActionLoading} aria-label={`Delete tag ${tag.name}`}>
                       {isActionLoading ? <Loader2 className="h-4 w-4 animate-spin"/> : <Trash2 size={14} />}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
           <div className="flex justify-end mt-3">
              {/* --- CORRECTED BUTTON VARIANT --- */}
              <Button variant="secondary" size="sm" onClick={toggleManageSection}>Close Management</Button>
           </div>
        </div>
      )}
    </div>
  );
};