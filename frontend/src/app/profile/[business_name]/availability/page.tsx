// frontend/src/app/profile/[business_name]/availability/page.tsx
"use client";

import { useEffect, useState, useCallback, FormEvent } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  CardFooter,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  ArrowLeft,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  PlusCircle,
  Trash2,
  Clock,
  Zap,
  Settings2,
  Edit,
  Save,
  CalendarDays, // Using CalendarDays as a more generic icon for the page title
} from "lucide-react";
import clsx from "clsx";

type AvailabilityStyle = "smart_hours" | "flexible_coordinator" | "manual_slots" | "";

interface SmartHoursConfig {
  weekdayStartTimeLocal: string; // HH:MM
  weekdayEndTimeLocal: string; // HH:MM
  exceptionsNote: string;
}

interface ManualRule {
  id: string; 
  dayOfWeek: string;
  startTimeLocal: string; // HH:MM
  endTimeLocal: string; // HH:MM
  isActive: boolean;
  isNew?: boolean;
}

interface AvailabilitySettingsData {
  availabilityStyle: AvailabilityStyle;
  smartHoursConfig?: SmartHoursConfig;
  manualRules?: {
    dayOfWeek: string;
    startTimeLocal: string;
    endTimeLocal: string;
    isActive: boolean;
    id?: string | number;
  }[];
}

const DAYS_OF_WEEK = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];
const DEFAULT_START_TIME = "09:00";
const DEFAULT_END_TIME = "17:00";

export default function AvailabilitySettingsPage() {
  const params = useParams();
  const router = useRouter();
  const businessSlug = params.business_name as string;

  const [businessId, setBusinessId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const [availabilityStyle, setAvailabilityStyle] = useState<AvailabilityStyle>("smart_hours");
  const [smartHoursConfig, setSmartHoursConfig] = useState<SmartHoursConfig>({
    weekdayStartTimeLocal: DEFAULT_START_TIME,
    weekdayEndTimeLocal: DEFAULT_END_TIME,
    exceptionsNote: "",
  });
  const [manualRules, setManualRules] = useState<ManualRule[]>([]);

  const [showManualRuleModal, setShowManualRuleModal] = useState(false);
  const [currentRuleToEdit, setCurrentRuleToEdit] = useState<Partial<ManualRule> | null>(null);
  const [isEditingRule, setIsEditingRule] = useState(false);


  useEffect(() => {
    if (businessSlug) {
      apiClient.get(`/business-profile/business-id/slug/${businessSlug}`)
        .then(res => {
          if (res.data?.business_id) {
            setBusinessId(res.data.business_id);
          } else {
            setError("Failed to identify business.");
            setIsLoading(false);
          }
        })
        .catch(err => {
          setError("Error fetching business ID. Please ensure you are logged in or the business exists.");
          console.error("Error fetching business ID:", err);
          setIsLoading(false);
        });
    }
  }, [businessSlug]);

  const fetchAvailabilitySettings = useCallback(async (bId: number) => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await apiClient.get<AvailabilitySettingsData>(`/business-profile/${bId}/availability-settings`);
      const settings = response.data;
      if (settings && settings.availabilityStyle) {
        setAvailabilityStyle(settings.availabilityStyle);
        if (settings.smartHoursConfig) setSmartHoursConfig(settings.smartHoursConfig);
        if (settings.manualRules) {
          setManualRules(settings.manualRules.map((rule, index) => ({
            ...rule,
            dayOfWeek: rule.dayOfWeek || DAYS_OF_WEEK[0],
            startTimeLocal: rule.startTimeLocal || DEFAULT_START_TIME,
            endTimeLocal: rule.endTimeLocal || DEFAULT_END_TIME,
            isActive: rule.isActive === undefined ? true : rule.isActive,
            id: String(rule.id || `loaded-${Date.now()}-${index}`), // Ensure unique string ID for loaded rules
          })));
        }
      } else {
        setAvailabilityStyle("smart_hours");
        setSmartHoursConfig({ weekdayStartTimeLocal: DEFAULT_START_TIME, weekdayEndTimeLocal: DEFAULT_END_TIME, exceptionsNote: "" });
        setManualRules([]);
      }
    } catch (err: any) {
      console.error("Error fetching availability settings:", err);
      if (err.response?.status === 404) {
        setError("No existing availability settings found. Please configure new settings.");
        setAvailabilityStyle("smart_hours"); 
      } else {
        setError("Could not load existing availability settings. Defaults will be shown.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [setIsLoading, setError, setAvailabilityStyle, setSmartHoursConfig, setManualRules]);


  useEffect(() => {
    if (businessId) {
      fetchAvailabilitySettings(businessId);
    }
  }, [businessId, fetchAvailabilitySettings]);

  const handleStyleChange = (newStyle: AvailabilityStyle) => {
    setAvailabilityStyle(newStyle);
    setError(null);
    setSuccessMessage(null);
  };

  const handleSmartHoursChange = (field: keyof SmartHoursConfig, value: string) => {
    setSmartHoursConfig(prev => ({ ...prev, [field]: value }));
  };

  const openAddManualRuleModal = () => {
    setCurrentRuleToEdit({
      id: `new-${Date.now()}`, 
      dayOfWeek: DAYS_OF_WEEK[0],
      startTimeLocal: DEFAULT_START_TIME,
      endTimeLocal: DEFAULT_END_TIME,
      isActive: true,
      isNew: true,
    });
    setIsEditingRule(false); 
    setShowManualRuleModal(true);
  };

  const openEditManualRuleModal = (rule: ManualRule) => {
    setCurrentRuleToEdit({ ...rule, isNew: false }); 
    setIsEditingRule(true);
    setShowManualRuleModal(true);
  };

  const handleSaveManualRule = (ruleToSave: ManualRule) => {
    if (!ruleToSave.dayOfWeek || !ruleToSave.startTimeLocal || !ruleToSave.endTimeLocal) {
        alert("Day, start time, and end time are required for a manual rule.");
        return;
    }
    if (ruleToSave.startTimeLocal >= ruleToSave.endTimeLocal) {
        alert("Start time must be before end time.");
        return;
    }

    setManualRules(prevRules => {
      const existingRuleIndex = prevRules.findIndex(r => r.id === ruleToSave.id);
      if (existingRuleIndex > -1) { 
        const updatedRules = [...prevRules];
        updatedRules[existingRuleIndex] = { ...ruleToSave, isNew: false };
        return updatedRules;
      } else {
        return [...prevRules, { ...ruleToSave, isNew: false }];
      }
    });
    setShowManualRuleModal(false);
    setCurrentRuleToEdit(null);
  };
  
  const handleDeleteManualRule = (ruleId: string) => {
    if (window.confirm("Are you sure you want to delete this availability slot?")) {
        setManualRules(prevRules => prevRules.filter(r => r.id !== ruleId));
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!businessId) {
      setError("Business ID not available. Cannot save settings.");
      return;
    }
    setIsSaving(true);
    setError(null);
    setSuccessMessage(null);

    const payload: Partial<AvailabilitySettingsData> = { availabilityStyle };
    if (availabilityStyle === "smart_hours") {
      payload.smartHoursConfig = smartHoursConfig;
    } else if (availabilityStyle === "manual_slots") {
      // Ensure 'id' is preserved as backend schema expects it, but remove 'isNew'
      payload.manualRules = manualRules.map(rule => {
        const { isNew, ...rest } = rule; // Destructure to remove isNew
        return rest; // Send all other properties including 'id'
      });
      console.log("handleSubmit: Payload for manual_slots:", payload.manualRules); // For debugging
    }

    try {
      await apiClient.put(`/business-profile/${businessId}/availability-settings`, payload);
      setSuccessMessage("Availability settings saved successfully!");
      if (businessId) fetchAvailabilitySettings(businessId); 
    } catch (err: any) {
      console.error("Error saving availability settings:", err);
      setError(err.response?.data?.detail || "An error occurred while saving settings.");
    } finally {
      setIsSaving(false);
    }
  };

  // Base dark theme classes (similar to your ProfilePage)
  const pageBgClass = "bg-slate-900"; // Or your nudge-gradient if it's a global class
  const textPrimaryClass = "text-white";
  const textSecondaryClass = "text-slate-300";
  const textMutedClass = "text-slate-400";
  const cardBgClass = "bg-[#1A1D2D]"; // From ProfilePage sections
  const cardBorderClass = "border-[#2A2F45]"; // From ProfilePage sections
  const inputBgClass = "bg-[#242842]"; // From ProfilePage inputs
  const inputBorderClass = "border-[#333959]"; // From ProfilePage inputs
  const inputFocusClass = "focus:border-emerald-500/70 focus:ring-1 focus:ring-emerald-500/70";

  if (isLoading && !businessId) { 
    return (
      <div className={`flex flex-col justify-center items-center min-h-screen p-4 text-center ${pageBgClass} ${textMutedClass}`}>
        <RefreshCw className="animate-spin h-8 w-8 text-emerald-400 mb-3" />
        <p>Loading Business Info...</p>
      </div>
    );
  }
  
  if (error && !businessId && !isLoading) { 
     return (
      <div className={`container mx-auto p-4 md:p-8 text-center ${pageBgClass}`}>
        <Card className={`max-w-md mx-auto mt-10 ${cardBgClass} ${cardBorderClass} shadow-xl`}>
            <CardHeader><CardTitle className="text-red-400 flex items-center justify-center"><AlertTriangle className="h-6 w-6 mr-2 shrink-0" /> Error</CardTitle></CardHeader>
            <CardContent><p className={textSecondaryClass}>{error}</p></CardContent>
            <CardFooter><Button onClick={() => router.back()} className="w-full bg-emerald-500 hover:bg-emerald-600 text-white"><ArrowLeft className="mr-2 h-4 w-4" /> Go Back</Button></CardFooter>
        </Card>
      </div>
    );
  }

  return (
    <div className={`min-h-screen ${pageBgClass} ${textPrimaryClass} py-12 px-4 sm:px-6 lg:px-8`}>
      <div className="container mx-auto max-w-3xl">
        <Button variant="ghost" onClick={() => router.back()} className={`mb-6 text-sm ${textMutedClass} hover:bg-slate-700 px-3 py-1.5`}>
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to Profile
        </Button>
        
        <div className="text-center mb-10">
          <h1 className={`text-3xl sm:text-4xl font-bold tracking-tight ${textPrimaryClass} flex items-center justify-center`}>
            <CalendarDays className="w-8 h-8 sm:w-10 sm:h-10 mr-3 text-emerald-400"/> {/* Changed icon */}
            Your AI Nudge: Availability Style
          </h1>
          <p className={`${textSecondaryClass} mt-3 text-lg max-w-2xl mx-auto`}>
            Choose how AI Nudge should understand and manage your appointment availability. This helps the AI suggest appropriate times to customers.
          </p>
        </div>

        {isLoading && businessId !== null && (
            <div className="flex flex-col justify-center items-center p-4 text-center my-8">
                <RefreshCw className={`animate-spin h-8 w-8 text-emerald-400 mb-3`} />
                <p className={textMutedClass}>Loading Your Settings...</p>
            </div>
        )}

        {!isLoading && businessId !== null && (
          <form onSubmit={handleSubmit} className="space-y-8">
            {error && !successMessage && (
              <div role="alert" className={`mb-6 p-4 bg-red-900/50 border border-red-700/60 text-red-300 text-sm rounded-lg flex items-center shadow`}>
                  <AlertTriangle className="h-5 w-5 mr-3 shrink-0" /> {error}
              </div>
            )}
            {successMessage && (
              <div role="alert" className={`mb-6 p-4 bg-green-900/50 border border-green-700/60 text-green-300 text-sm rounded-lg flex items-center shadow`}>
                  <CheckCircle2 className="h-5 w-5 mr-3 shrink-0" /> {successMessage}
              </div>
            )}

            <Card className={`${cardBgClass} ${cardBorderClass} shadow-xl rounded-xl`}>
              <CardHeader className="p-6">
                <CardTitle className={textPrimaryClass}>Choose Your Availability Style</CardTitle>
                <CardDescription className={textMutedClass}>Select one primary way AI Nudge will handle your schedule.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6 p-6 pt-0 sm:pt-0"> {/* Adjusted padding */}
                {/* Option A: Smart Hours */}
                <div
                  className={clsx(
                    "p-4 border rounded-lg cursor-pointer transition-all",
                    availabilityStyle === "smart_hours" ? "border-emerald-500 ring-2 ring-emerald-500 bg-[#242842]/50" : `${cardBorderClass} hover:border-slate-500`
                  )}
                  onClick={() => handleStyleChange("smart_hours")}
                  role="button" tabIndex={0} onKeyPress={(e) => e.key === 'Enter' && handleStyleChange("smart_hours")}
                >
                  <div className="flex items-center mb-2">
                    <Clock className="w-6 h-6 mr-3 text-emerald-400" />
                    <h3 className={`text-lg font-semibold ${textPrimaryClass}`}>Smart Hours Helper</h3>
                  </div>
                  <p className={`text-sm ${textSecondaryClass} mb-3`}>
                    I have typical business hours (e.g., Mon-Fri, 9-5). AI uses this as a guide.
                  </p>
                  {availabilityStyle === "smart_hours" && (
                    <div className={`mt-4 space-y-4 p-4 bg-[#0F1221]/50 rounded-md border ${cardBorderClass}`}>
                      <p className={`text-sm font-medium ${textSecondaryClass}`}>My usual weekdays are roughly:</p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-end">
                        <div>
                          <Label htmlFor="smartHoursStart" className={`text-xs ${textMutedClass}`}>From</Label>
                          <Input
                            type="time" id="smartHoursStart" name="smartHoursStart"
                            value={smartHoursConfig.weekdayStartTimeLocal}
                            onChange={(e) => handleSmartHoursChange("weekdayStartTimeLocal", e.target.value)}
                            className={`${inputBgClass} ${inputBorderClass} ${textPrimaryClass} ${inputFocusClass}`}
                          />
                        </div>
                        <div>
                          <Label htmlFor="smartHoursEnd" className={`text-xs ${textMutedClass}`}>To</Label>
                          <Input
                            type="time" id="smartHoursEnd" name="smartHoursEnd"
                            value={smartHoursConfig.weekdayEndTimeLocal}
                            onChange={(e) => handleSmartHoursChange("weekdayEndTimeLocal", e.target.value)}
                            className={`${inputBgClass} ${inputBorderClass} ${textPrimaryClass} ${inputFocusClass}`}
                          />
                        </div>
                      </div>
                       <div>
                          <Label htmlFor="smartHoursExceptions" className={`text-xs ${textMutedClass}`}>
                            Regular days off or major exceptions (optional)
                          </Label>
                          <Textarea
                            id="smartHoursExceptions" name="smartHoursExceptions"
                            placeholder="e.g., closed Wednesdays, lunch 12-1pm daily"
                            value={smartHoursConfig.exceptionsNote}
                            onChange={(e) => handleSmartHoursChange("exceptionsNote", e.target.value)}
                            rows={2}
                            className={`mt-1 ${inputBgClass} ${inputBorderClass} ${textPrimaryClass} ${inputFocusClass}`}
                          />
                           <p className={`text-xs ${textMutedClass} mt-1`}>AI will parse this to help define your available times.</p>
                        </div>
                    </div>
                  )}
                </div>

                {/* Option B: Flexible Coordinator */}
                <div
                  className={clsx(
                    "p-4 border rounded-lg cursor-pointer transition-all",
                    availabilityStyle === "flexible_coordinator" ? "border-sky-500 ring-2 ring-sky-500 bg-[#242842]/50" : `${cardBorderClass} hover:border-slate-500`
                  )}
                  onClick={() => handleStyleChange("flexible_coordinator")}
                  role="button" tabIndex={0} onKeyPress={(e) => e.key === 'Enter' && handleStyleChange("flexible_coordinator")}
                >
                  <div className="flex items-center mb-2">
                     <Zap className="w-6 h-6 mr-3 text-sky-400" /> 
                    <h3 className={`text-lg font-semibold ${textPrimaryClass}`}>Flexible Coordinator</h3>
                  </div>
                  <p className={`text-sm ${textSecondaryClass}`}>
                    My schedule is very flexible. AI will suggest times based on customer requests, and I'll approve each one.
                  </p>
                  {availabilityStyle === "flexible_coordinator" && (
                    <div className={`mt-3 p-3 bg-[#0F1221]/50 rounded-md text-sm ${textSecondaryClass}`}>
                      ✓ AI Nudge will help coordinate times case-by-case. No specific hours needed from you here.
                    </div>
                  )}
                </div>

                {/* Option C: Manual Slots */}
                <div
                  className={clsx(
                    "p-4 border rounded-lg cursor-pointer transition-all",
                    availabilityStyle === "manual_slots" ? "border-orange-500 ring-2 ring-orange-500 bg-[#242842]/50" : `${cardBorderClass} hover:border-slate-500`
                  )}
                  onClick={() => handleStyleChange("manual_slots")}
                  role="button" tabIndex={0} onKeyPress={(e) => e.key === 'Enter' && handleStyleChange("manual_slots")}
                >
                  <div className="flex items-center mb-2">
                    <Settings2 className="w-6 h-6 mr-3 text-orange-400" /> 
                    <h3 className={`text-lg font-semibold ${textPrimaryClass}`}>Manual Slots (Advanced)</h3>
                  </div>
                  <p className={`text-sm ${textSecondaryClass}`}>
                    I want to define specific recurring time slots for each day of the week.
                  </p>
                  {availabilityStyle === "manual_slots" && (
                    <div className={`mt-4 p-4 bg-[#0F1221]/50 rounded-md border ${cardBorderClass}`}>
                      <h4 className={`text-md font-semibold ${textPrimaryClass} mb-3`}>Your Manual Recurring Slots:</h4>
                      <div className="space-y-3">
                        {manualRules.length === 0 && (
                             <p className={`text-sm ${textMutedClass} text-center py-3`}>No manual slots defined yet.</p>
                        )}
                        {manualRules.map((rule) => (
                          <Card key={rule.id} className={`p-3 ${inputBgClass} ${cardBorderClass} flex items-center justify-between space-x-2`}>
                            <div className="flex-grow">
                                <p className={`text-sm font-medium ${textSecondaryClass}`}>
                                    {rule.dayOfWeek}: {rule.startTimeLocal} - {rule.endTimeLocal}
                                </p>
                                <p className={clsx("text-xs", rule.isActive ? "text-green-400" : textMutedClass)}>
                                    {rule.isActive ? "Active" : "Inactive"}
                                </p>
                            </div>
                            <div className="flex items-center space-x-2 shrink-0">
                                <Button type="button" variant="secondary" size="icon" onClick={() => openEditManualRuleModal(rule)} aria-label="Edit rule" className={`border-slate-600 hover:bg-slate-700 ${textSecondaryClass}`}>
                                    <Edit className="w-4 h-4"/>
                                </Button>
                                <Button type="button" variant="destructive" size="icon" onClick={() => handleDeleteManualRule(rule.id)} aria-label="Delete rule">
                                    <Trash2 className="w-4 h-4"/>
                                </Button>
                            </div>
                          </Card>
                        ))}
                      </div>
                      <Button type="button" variant="secondary" size="sm" className={`mt-4 w-full sm:w-auto border-slate-600 hover:bg-slate-700 ${textSecondaryClass}`} onClick={openAddManualRuleModal}>
                        <PlusCircle className="w-4 h-4 mr-2" /> Add Manual Slot
                      </Button>
                    </div>
                  )}
                </div>
              </CardContent>
              <CardFooter className={`border-t ${cardBorderClass} px-6 py-4 mt-2`}>
                <Button type="submit" disabled={isSaving || isLoading || !businessId} 
                        className="w-full sm:w-auto bg-emerald-500 hover:bg-emerald-600 text-white font-semibold">
                  {isSaving ? <><RefreshCw className="mr-2 h-4 w-4 animate-spin" /> Saving Settings...</> : "Save Availability Settings"}
                </Button>
              </CardFooter>
            </Card>
          </form>
        )}

        {/* Manual Rule Add/Edit Modal */}
        {showManualRuleModal && currentRuleToEdit && (
            <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4" onClick={() => setShowManualRuleModal(false)}>
                <Card className={`w-full max-w-md ${cardBgClass} ${cardBorderClass} shadow-2xl`} onClick={(e) => e.stopPropagation()}>
                    <CardHeader>
                        <CardTitle className={textPrimaryClass}>{isEditingRule ? "Edit" : "Add"} Manual Availability Slot</CardTitle>
                        <CardDescription className={textMutedClass}>Define a recurring time slot for a specific day.</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div>
                            <Label htmlFor="ruleDayOfWeek" className={textSecondaryClass}>Day of the Week</Label>
                            <Select
                                value={currentRuleToEdit.dayOfWeek}
                                onValueChange={(value: string) => setCurrentRuleToEdit(prev => prev ? {...prev, dayOfWeek: value} : null)}
                            >
                                <SelectTrigger id="ruleDayOfWeek" className={`${inputBgClass} ${inputBorderClass} ${textPrimaryClass} ${inputFocusClass}`}>
                                    <SelectValue placeholder="Select a day" />
                                </SelectTrigger>
                                <SelectContent className={`${cardBgClass} ${inputBorderClass} ${textPrimaryClass}`}>
                                    {DAYS_OF_WEEK.map(day => <SelectItem key={day} value={day} className="hover:bg-slate-700">{day}</SelectItem>)}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <Label htmlFor="ruleStartTime" className={textSecondaryClass}>Start Time</Label>
                                <Input type="time" id="ruleStartTime" value={currentRuleToEdit.startTimeLocal || ""}
                                       onChange={(e) => setCurrentRuleToEdit(prev => prev ? {...prev, startTimeLocal: e.target.value} : null)}
                                       className={`${inputBgClass} ${inputBorderClass} ${textPrimaryClass} ${inputFocusClass}`}
                                />
                            </div>
                            <div>
                                <Label htmlFor="ruleEndTime" className={textSecondaryClass}>End Time</Label>
                                <Input type="time" id="ruleEndTime" value={currentRuleToEdit.endTimeLocal || ""}
                                       onChange={(e) => setCurrentRuleToEdit(prev => prev ? {...prev, endTimeLocal: e.target.value} : null)}
                                       className={`${inputBgClass} ${inputBorderClass} ${textPrimaryClass} ${inputFocusClass}`}
                                />
                            </div>
                        </div>
                        <div className="flex items-center space-x-2 pt-2">
                            <Switch id="ruleIsActive" checked={!!currentRuleToEdit.isActive}
                                    onCheckedChange={(checked) => setCurrentRuleToEdit(prev => prev ? {...prev, isActive: checked} : null)}
                                    className="data-[state=checked]:bg-emerald-500"
                            />
                            <Label htmlFor="ruleIsActive" className={`text-sm ${textSecondaryClass}`}>Slot is Active</Label>
                        </div>
                    </CardContent>
                    <CardFooter className={`flex justify-end space-x-3 border-t ${cardBorderClass} pt-4 pb-4 pr-4`}>
                        <Button type="button" variant="secondary" onClick={() => setShowManualRuleModal(false)} className={`border-slate-600 hover:bg-slate-700 ${textSecondaryClass}`}>Cancel</Button>
                        <Button type="button" onClick={() => currentRuleToEdit && handleSaveManualRule(currentRuleToEdit as ManualRule)} className="bg-emerald-500 hover:bg-emerald-600 text-white">
                           <Save className="w-4 h-4 mr-2"/> {isEditingRule ? "Save Changes" : "Add Slot"}
                        </Button>
                    </CardFooter>
                </Card>
            </div>
        )}
      </div>
    </div>
  );
}