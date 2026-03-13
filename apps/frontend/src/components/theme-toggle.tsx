import { Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/hooks/use-theme";

interface ThemeToggleProps {
  showLabel?: boolean;
}

export function ThemeToggle({ showLabel = false }: ThemeToggleProps) {
  const { resolvedTheme, setTheme, theme } = useTheme();

  const handleToggle = () => {
    // If on system, switch to the opposite of what system resolved to.
    // If on explicit light/dark, toggle to the other.
    const next = resolvedTheme === "dark" ? "light" : "dark";
    setTheme(next);
  };

  const label =
    theme === "system"
      ? "System theme"
      : resolvedTheme === "dark"
        ? "Dark mode"
        : "Light mode";

  return (
    <Button
      variant="ghost"
      size={showLabel ? "sm" : "icon-sm"}
      onClick={handleToggle}
      aria-label="Toggle theme"
      data-testid="theme-toggle"
      title={label}
    >
      {resolvedTheme === "dark" ? (
        <Moon className="size-4" />
      ) : (
        <Sun className="size-4" />
      )}
      {showLabel && <span>{label}</span>}
    </Button>
  );
}
