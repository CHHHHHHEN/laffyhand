interface SpinnerProps {
  size?: "sm" | "md" | "lg"
  className?: string
}

const sizeStyles: Record<string, string> = {
  sm: "h-4 w-4 border-[2.5px]",
  md: "h-5 w-5 border-[2.5px]",
  lg: "h-7 w-7 border-[3px]",
}

export function Spinner({ size = "md", className = "" }: SpinnerProps) {
  return (
    <div
      className={`animate-spin rounded-full border-gray-200 dark:border-gray-700 border-t-blue-500 dark:border-t-blue-400 ${sizeStyles[size]} ${className}`}
    />
  )
}
