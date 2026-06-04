import type { ButtonHTMLAttributes } from "react"

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger"
  size?: "sm" | "md" | "lg"
}

const variantStyles: Record<string, string> = {
  primary:
    "bg-[var(--accent)] text-white hover:opacity-90 active:opacity-80 disabled:opacity-40",
  secondary:
    "bg-[var(--bg-deep)] text-[var(--text-base)] hover:bg-[var(--bg-layer-1)] active:bg-[var(--bg-layer-2)] border border-[var(--border-base)]",
  ghost:
    "bg-transparent text-[var(--text-muted)] hover:text-[var(--text-base)] hover:bg-[var(--overlay-hover)]",
  danger:
    "bg-[var(--state-danger-fg)] text-white hover:opacity-90 active:opacity-80 disabled:opacity-40",
}

const sizeStyles: Record<string, string> = {
  sm: "px-2.5 py-1 text-xs rounded-md gap-1",
  md: "px-3.5 py-1.5 text-sm rounded-md gap-1.5",
  lg: "px-5 py-2.5 text-base rounded-lg gap-2",
}

export function Button({
  variant = "primary",
  size = "md",
  className = "",
  disabled,
  children,
  style,
  ...props
}: ButtonProps) {
  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center transition-all duration-150 cursor-pointer disabled:cursor-not-allowed disabled:opacity-60 select-none ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
      disabled={disabled}
      style={{ fontWeight: 500, ...style }}
      {...props}
    >
      {children}
    </button>
  )
}
