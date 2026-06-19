import { cn } from "@/lib/utils"

export function BrandMark({
  className,
  iconClassName,
}: {
  className?: string
  iconClassName?: string
}) {
  return (
    <span
      aria-hidden="true"
      className={cn("inline-flex size-7 items-center justify-center text-[#171310] dark:text-[#faf7f1]", className)}
    >
      <svg
        viewBox="0 0 64 64"
        className={cn("size-6", iconClassName)}
        fill="none"
        role="img"
      >
        <path
          d="M18 47.5 32 14.5 46 47.5M24 34.5H40"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="7"
        />
        <circle cx="32" cy="14.5" r="7" fill="currentColor" />
        <circle cx="18" cy="47.5" r="7" fill="currentColor" />
        <circle cx="46" cy="47.5" r="7" fill="currentColor" />
        <path
          d="m43.5 15.5 4-2.2 1.3-4.3 1.3 4.3 4 2.2-4 2.2-1.3 4.3-1.3-4.3-4-2.2Z"
          fill="currentColor"
        />
      </svg>
    </span>
  )
}
