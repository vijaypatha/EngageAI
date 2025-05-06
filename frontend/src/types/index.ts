// Define the Tag type
export interface Tag {
    id: number;
    name: string;
  }
  
  // Define the Customer structure
  export interface Customer {
    id: number;
    customer_name: string;
    phone: string;
    lifecycle_stage: string;
    pain_points: string;
    interaction_history: string;
    business_id: number;
    timezone?: string | null;
    opted_in?: boolean | null;
    is_generating_roadmap?: boolean | null;
    last_generation_attempt?: string | null;
    created_at: string;
    updated_at?: string | null;
    latest_consent_status?: string | null;
    latest_consent_updated?: string | null;
    tags?: Tag[] | null;
  }
  
  // Add other shared types here...