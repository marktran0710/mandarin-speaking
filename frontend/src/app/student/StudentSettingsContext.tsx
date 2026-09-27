import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { canUseDatabase } from "../../services/database";
import {
  changeStudentPassword,
  getStudentSettings,
  updateStudentSettings,
  type StudentSettings,
  type StudentSettingsUpdate,
} from "../../services/api/student-settings";
import { getStudentId } from "../../utils/studentSession";

export const DEFAULT_STUDENT_SETTINGS: StudentSettings = {
  studentMascot: "male",
  partnerMascot: "fox",
  voiceHintMode: "auto",
};

interface StudentSettingsContextValue {
  settings: StudentSettings;
  isLoading: boolean;
  isSaving: boolean;
  error: string | null;
  saveSettings: (update: StudentSettingsUpdate) => Promise<StudentSettings>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  clearError: () => void;
}

const StudentSettingsContext = createContext<StudentSettingsContextValue | null>(null);

export function StudentSettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState(DEFAULT_STUDENT_SETTINGS);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      if (!getStudentId() || !canUseDatabase()) {
        setIsLoading(false);
        return;
      }
      try {
        const loaded = await getStudentSettings();
        if (!cancelled) setSettings(loaded);
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "Could not load student settings.");
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };
    void load();
    return () => { cancelled = true; };
  }, []);

  const saveSettings = useCallback(async (update: StudentSettingsUpdate) => {
    setIsSaving(true);
    setError(null);
    try {
      const saved = canUseDatabase() && getStudentId()
        ? await updateStudentSettings(update)
        : { ...settings, ...update } as StudentSettings;
      setSettings(saved);
      return saved;
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Could not save student settings.";
      setError(message);
      throw cause;
    } finally {
      setIsSaving(false);
    }
  }, [settings]);

  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    setIsSaving(true);
    setError(null);
    try {
      await changeStudentPassword(currentPassword, newPassword);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Could not change password.";
      setError(message);
      throw cause;
    } finally {
      setIsSaving(false);
    }
  }, []);

  const clearError = useCallback(() => setError(null), []);
  const value = useMemo(() => ({
    settings,
    isLoading,
    isSaving,
    error,
    saveSettings,
    changePassword,
    clearError,
  }), [settings, isLoading, isSaving, error, saveSettings, changePassword, clearError]);

  return <StudentSettingsContext.Provider value={value}>{children}</StudentSettingsContext.Provider>;
}

export function useStudentSettings() {
  const value = useContext(StudentSettingsContext);
  if (!value) throw new Error("useStudentSettings must be used inside StudentSettingsProvider");
  return value;
}

/** Conversation history can also render in teacher/debug tests outside the
 * student shell, so avatar selection has a safe legacy-default fallback. */
export function useStudentSettingsValue() {
  return useContext(StudentSettingsContext)?.settings ?? DEFAULT_STUDENT_SETTINGS;
}

