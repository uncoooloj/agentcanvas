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
          d="M18 48 32 15 46 48"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="5"
        />
        <circle cx="32" cy="15" r="6" fill="var(--logo-fill, hsl(var(--background)))" stroke="currentColor" strokeWidth="4.5" />
        <circle cx="18" cy="48" r="6" fill="var(--logo-fill, hsl(var(--background)))" stroke="currentColor" strokeWidth="4.5" />
        <circle cx="46" cy="48" r="6" fill="var(--logo-fill, hsl(var(--background)))" stroke="currentColor" strokeWidth="4.5" />
        <path
          d="m43.5 12.5 4.4-2.1 2-4.4 2 4.4 4.4 2.1-4.4 2.1-2 4.4-2-4.4-4.4-2.1Z"
          fill="currentColor"
        />
      </svg>
    </span>
  )
}
