import type { ButtonHTMLAttributes } from "react"

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger"
  size?: "sm" | "md" | "lg"
}

const variantStyles: Record<string, string> = {
  primary:
    "bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800 disabled:bg-blue-400/60 shadow-sm hover:shadow active:shadow-none",
  secondary:
    "bg-gray-100 text-gray-700 hover:bg-gray-200 active:bg-gray-300 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600 dark:active:bg-gray-500 border border-gray-200 dark:border-gray-600",
  ghost:
    "bg-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-300 dark:hover:bg-gray-800",
  danger:
    "bg-red-600 text-white hover:bg-red-700 active:bg-red-800 disabled:bg-red-400/60 shadow-sm hover:shadow",
}

const sizeStyles: Record<string, string> = {
  sm: "px-2.5 py-1 text-xs rounded-lg gap-1",
  md: "px-3.5 py-1.5 text-sm rounded-lg gap-1.5",
  lg: "px-5 py-2.5 text-base rounded-xl gap-2",
}

export function Button({
  variant = "primary",
  size = "md",
  className = "",
  disabled,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center font-medium transition-all duration-150 cursor-pointer disabled:cursor-not-allowed disabled:opacity-60 select-none ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
      disabled={disabled}
      {...props}
    >
      {children}
    </button>
  )
}
