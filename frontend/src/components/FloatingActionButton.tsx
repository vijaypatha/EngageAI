// File Path: frontend/src/components/FloatingActionButton.tsx
import React from 'react';
import clsx from 'clsx';

// Define the properties (props) that this component accepts
interface FloatingActionButtonProps {
  onClick: () => void; // Function to call when the button is clicked
  icon: React.ReactNode; // The icon to display inside the button (e.g., <UserPlus />)
  label?: string; // Optional text label displayed next to the icon
  tooltip?: string; // Optional text that appears on hover
  className?: string; // Allows for additional custom styling
  pulsing?: boolean; // If true, the button will have a pulsing animation
}

/**
 * A reusable Floating Action Button (FAB) component, typically fixed to the bottom-right of the screen.
 * It serves as a primary call-to-action.
 */
export const FloatingActionButton: React.FC<FloatingActionButtonProps> = ({
  onClick,
  icon,
  label,
  tooltip,
  className,
  pulsing = false, // Default pulsing to false
}) => {
  return (
    <button
      onClick={onClick}
      className={clsx(
        // Base styles for the button
        "fixed z-50 bottom-4 right-4 bg-blue-600 hover:bg-blue-700 text-white rounded-full shadow-lg p-4 flex items-center justify-center transition-all duration-300",
        // Conditional style for the pulsing animation
        pulsing && "animate-pulse",
        // Allow for custom classes to be passed in
        className
      )}
      title={tooltip}
      aria-label={label || tooltip}
    >
      {icon}
      {label && <span className="ml-2 font-semibold text-sm hidden sm:inline">{label}</span>}
    </button>
  );
};