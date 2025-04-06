import * as React from "react";
import { Label as LabelPrimitive } from "@radix-ui/react-label";
import { cn } from "@/lib/utils";

const Label = React.forwardRef<
  React.ElementRef<typeof LabelPrimitive>,
  React.ComponentPropsWithoutRef<typeof LabelPrimitive>
>(({ className, ...props }, ref) => (
  <LabelPrimitive
    ref={ref}
    className={cn("block text-sm font-medium text-gray-700", className)}
    {...props}
  />
));

Label.displayName = "Label";

export { Label };
