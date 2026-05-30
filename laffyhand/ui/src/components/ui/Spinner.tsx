interface SpinnerProps {
  size?: "sm" | "md" | "lg"
  className?: string
}

const sizeStyles: Record<string, string> = {
  sm: "h-4 w-4 border-2",
  md: "h-6 w-6 border-2",
  lg: "h-8 w-8 border-3",
}

export function Spinner({ size = "md", className = "" }: SpinnerProps) {
  return (
    <div
      className={`animate-spin rounded-full border-gray-300 border-t-blue-600 ${sizeStyles[size]} ${className}`}
    />
  )
}
