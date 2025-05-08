// src/lib/phoneUtils.ts

/**
 * Formats a phone number input string towards E.164, primarily for display
 * during user input. Allows partial input.
 * Prioritizes adding +1 for likely US numbers (10 digits or 11 starting with 1).
 */
export const formatPhoneNumberForDisplay = (value: string): string => {
    if (!value) return '';
  
    // Check if the input already starts with '+'
    const startsWithPlus = value.trim().startsWith('+');
  
    // Get all digits from the input string
    let digits = value.replace(/\D/g, '');
  
    // Case 1: Input starts with '+' - Keep '+' and only the digits that followed it
    if (startsWithPlus) {
      // Return the '+' plus the cleaned digits that were originally after the '+'
      // Example: "+1 (123) 456" -> "+1123456"
      const originalDigitsAfterPlus = value.substring(1).replace(/\D/g, '');
      return `+${originalDigitsAfterPlus}`;
    }
  
    // Case 2: Input does NOT start with '+'
    // User typed 10 digits -> Format as +1XXXXXXXXXX
    if (digits.length === 10) {
      return `+1${digits}`;
    }
    // User typed 11 digits AND the first digit is '1' -> Format as +1XXXXXXXXXX
    // (Treating '1xxxxxxxxxx' as a US number needing '+1')
    if (digits.length === 11 && digits.startsWith('1')) {
      // return `+${digits}`; // This would be +1xxxxxxxxxx
      return `+1${digits.substring(1)}`; // This ensures +1 followed by the 10 digits
    }
  
    // Fallback: If it doesn't match the above patterns (e.g., fewer digits,
    // 11 digits not starting with 1, contains non-digit chars after cleaning)
    // return just the digits to allow the user to continue typing without interference.
    return digits;
  };
  
  /**
   * A stricter formatter/validator often used just before sending to backend,
   * ensuring the number matches E.164 (+1XXXXXXXXXX for US).
   * Returns empty string if format is not convertible.
   */
  export const ensureE164Format = (value: string): string => {
      if (!value) return '';
      const startsWithPlus = value.trim().startsWith('+');
      let digits = value.replace(/\D/g, '');
  
      if (!startsWithPlus && digits.length === 10) {
          return `+1${digits}`;
      }
      if (!startsWithPlus && digits.length === 11 && digits.startsWith('1')) {
          return `+1${digits.substring(1)}`; // Or return `+${digits}`
      }
      if (startsWithPlus) {
          const originalDigitsAfterPlus = value.substring(1).replace(/\D/g, '');
          // Basic check for common US E.164 length after cleaning
          if (originalDigitsAfterPlus.startsWith('1') && originalDigitsAfterPlus.length === 11) {
               return `+${originalDigitsAfterPlus}`; // Already like +1xxxxxxxxxx
          }
           // Add more checks for other international E.164 if needed
      }
       // If it doesn't result in a valid format we recognize, return empty or handle error
       // For now, just attempt basic E.164 prefix
       if (digits.length >= 10) { // At least 10 digits
          return `+${digits}`; // Generic fallback prefix
       }
  
      return ''; // Indicate invalid format if none of the above match
  }