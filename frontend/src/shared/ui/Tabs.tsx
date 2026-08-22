import type { KeyboardEvent, ReactNode } from "react";

export interface TabItem<T extends string> {
  id: T;
  label: ReactNode;
  disabled?: boolean;
}

export interface TabsProps<T extends string> {
  items: readonly TabItem<T>[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
  idPrefix?: string;
}

function isArrowKey(key: string): boolean {
  return key === "ArrowRight" || key === "ArrowDown" || key === "ArrowLeft" || key === "ArrowUp";
}

export default function Tabs<T extends string>({
  items,
  value,
  onChange,
  ariaLabel,
  idPrefix = "tab",
}: TabsProps<T>) {
  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (!isArrowKey(event.key)) return;
    event.preventDefault();
    const direction = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : -1;
    const enabled = items.filter((item) => !item.disabled);
    const current = enabled.findIndex((item) => item.id === items[index].id);
    const next = enabled[(current + direction + enabled.length) % enabled.length];
    if (next) {
      onChange(next.id);
      document.getElementById(`${idPrefix}-${next.id}`)?.focus();
    }
  };

  return (
    <div className="ui-tabs" role="tablist" aria-label={ariaLabel}>
      {items.map((item, index) => (
        <button
          key={item.id}
          id={`${idPrefix}-${item.id}`}
          type="button"
          role="tab"
          aria-selected={value === item.id}
          aria-disabled={item.disabled || undefined}
          tabIndex={value === item.id ? 0 : -1}
          disabled={item.disabled}
          className={`ui-tab${value === item.id ? " is-active" : ""}`}
          onClick={() => onChange(item.id)}
          onKeyDown={(event) => handleKeyDown(event, index)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
