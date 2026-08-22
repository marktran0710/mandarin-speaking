import { useEffect, type PropsWithChildren, type ReactNode } from "react";

export interface ModalProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}

export default function Modal({ open, title, onClose, children }: PropsWithChildren<ModalProps>) {
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose, open]);

  if (!open) return null;
  return (
    <div className="ui-modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="ui-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="ui-modal-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="ui-modal-header">
          <h2 id="ui-modal-title">{title}</h2>
          <button type="button" className="ui-modal-close" aria-label="Close" onClick={onClose}>×</button>
        </div>
        <div className="ui-modal-body">{children}</div>
      </section>
    </div>
  );
}
