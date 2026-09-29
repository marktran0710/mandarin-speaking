import { useEffect, useState, type CSSProperties, type FormEvent, type ReactNode } from "react";
import StudentButton from "@shared/ui/student/StudentButton";
import StudentIcon from "@shared/ui/student/StudentIcon";
import StudentPage from "@shared/ui/student/StudentPage";
import StudentPageHeader from "@shared/ui/student/StudentPageHeader";
import StudentSection from "@shared/ui/student/StudentSection";
import StudentStatusPill from "@shared/ui/student/StudentStatusPill";
import StudentSystemText from "@shared/ui/student/StudentSystemText";
import { useStudentSettings } from "./StudentSettingsContext";
import type { PartnerMascot, StudentMascot, VoiceHintMode } from "../../services/api/student-settings";
import "./StudentSettingsPage.css";

type PreviewMascot = StudentMascot | PartnerMascot;

const mascotFiles: Record<PreviewMascot, string> = {
  male: "beard",
  female: "ballerina",
  fox: "fox",
};

function mascotStyle(mascot: PreviewMascot): CSSProperties {
  return {
    backgroundImage: `url(${import.meta.env.BASE_URL}mascots/${mascotFiles[mascot]}-directions.webp)`,
  };
}

function MascotChoice({ mascot, selected, label, onSelect }: { mascot: PreviewMascot; selected: boolean; label: ReactNode; onSelect: () => void }) {
  return (
    <label className={`sa-settings__choice ${selected ? "is-selected" : ""}`}>
      <input type="radio" checked={selected} onChange={onSelect} />
      <span className="sa-settings__choice-preview" style={mascotStyle(mascot)} aria-hidden="true" />
      <span className="sa-settings__choice-label">{label}</span>
    </label>
  );
}

export default function StudentSettingsPage({ onRequireRelogin }: { onRequireRelogin: () => void }) {
  const { settings, isLoading, isSaving, error, saveSettings, changePassword, clearError } = useStudentSettings();
  const [draft, setDraft] = useState(settings);
  const [settingsStatus, setSettingsStatus] = useState<"idle" | "saved">("idle");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordError, setPasswordError] = useState<"required" | "mismatch" | null>(null);

  useEffect(() => setDraft(settings), [settings]);

  const save = async () => {
    clearError();
    setSettingsStatus("idle");
    try {
      await saveSettings(draft);
      setSettingsStatus("saved");
    } catch {
      setSettingsStatus("idle");
    }
  };

  const submitPassword = async (event: FormEvent) => {
    event.preventDefault();
    setPasswordError(null);
    clearError();
    if (!currentPassword || !newPassword || !confirmPassword) {
      setPasswordError("required");
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError("mismatch");
      return;
    }
    try {
      await changePassword(currentPassword, newPassword);
      onRequireRelogin();
    } catch {
      // Keep the current session for wrong-password and validation errors.
    }
  };

  if (isLoading) {
    return <StudentPage layout="task" header={<StudentPageHeader eyebrowKey="settings" titleKey="settings" />} state="loading" />;
  }

  return (
    <StudentPage
      layout="task"
      className="sa-settings-page"
      header={<StudentPageHeader eyebrowKey="settings" titleKey="settings" subtitle={<span>Choose how your learning space looks and how the experimental voice comparison is measured.</span>} />}
    >
      <div className="sa-settings__stack">
        <StudentSection variant="panel" className="sa-settings__group">
          <div className="sa-settings__group-heading">
            <div>
              <p className="sa-settings__eyebrow"><StudentIcon name="face-neutral" size={16} role="decorative" /><StudentSystemText k="characterSettings" /></p>
              <h2><StudentSystemText k="studentAvatar" /></h2>
            </div>
            <StudentStatusPill tone="info"><StudentSystemText k={settings.studentMascot} withinControl /></StudentStatusPill>
          </div>
          <div className="sa-settings__choices sa-settings__choices--two">
            <MascotChoice mascot="male" selected={draft.studentMascot === "male"} onSelect={() => setDraft((value) => ({ ...value, studentMascot: "male" }))} label={<StudentSystemText k="male" />} />
            <MascotChoice mascot="female" selected={draft.studentMascot === "female"} onSelect={() => setDraft((value) => ({ ...value, studentMascot: "female" }))} label={<StudentSystemText k="female" />} />
          </div>
          <div className="sa-settings__subgroup">
            <h2><StudentSystemText k="conversationPartner" /></h2>
            <div className="sa-settings__choices sa-settings__choices--three">
              <MascotChoice mascot="fox" selected={draft.partnerMascot === "fox"} onSelect={() => setDraft((value) => ({ ...value, partnerMascot: "fox" }))} label={<StudentSystemText k="fox" />} />
              <MascotChoice mascot="male" selected={draft.partnerMascot === "male"} onSelect={() => setDraft((value) => ({ ...value, partnerMascot: "male" }))} label={<StudentSystemText k="male" />} />
              <MascotChoice mascot="female" selected={draft.partnerMascot === "female"} onSelect={() => setDraft((value) => ({ ...value, partnerMascot: "female" }))} label={<StudentSystemText k="female" />} />
            </div>
          </div>
          <div className="sa-settings__actions">
            {settingsStatus === "saved" && <StudentStatusPill tone="success"><StudentSystemText k="settingsSaved" withinControl /></StudentStatusPill>}
            {error && <p className="sa-settings__error" role="alert">{error}</p>}
            <StudentButton variant="primary" icon="check" onClick={() => void save()} disabled={isSaving}>
              <StudentSystemText k={isSaving ? "saving" : "saveSettings"} withinControl />
            </StudentButton>
          </div>
        </StudentSection>

        <StudentSection variant="panel" className="sa-settings__group">
          <div className="sa-settings__group-heading">
            <div>
              <p className="sa-settings__eyebrow"><StudentIcon name="graphic_eq" size={16} role="decorative" /><StudentSystemText k="voiceAnalysis" /></p>
              <h2><StudentSystemText k="voiceAnalysis" /></h2>
            </div>
          </div>
          <div className="sa-settings__radio-list">
            {(["auto", "avatar"] as VoiceHintMode[]).map((mode) => (
              <label className="sa-settings__radio-row" key={mode}>
                <input type="radio" name="voice-hint-mode" checked={draft.voiceHintMode === mode} onChange={() => setDraft((value) => ({ ...value, voiceHintMode: mode }))} />
                <span><strong><StudentSystemText k={mode === "auto" ? "automatic" : "useMyRole"} /></strong><small>{mode === "auto" ? "Keep the primary 75–500 Hz measurement only." : "Add a male/female comparison range; it never changes score or unlocks."}</small></span>
              </label>
            ))}
          </div>
        </StudentSection>

        <StudentSection variant="panel" className="sa-settings__group">
          <div className="sa-settings__group-heading">
            <div>
              <p className="sa-settings__eyebrow"><StudentIcon name="lock" size={16} role="decorative" /><StudentSystemText k="changePassword" /></p>
              <h2><StudentSystemText k="changePassword" /></h2>
            </div>
          </div>
          <form className="sa-settings__password-form" onSubmit={(event) => void submitPassword(event)}>
            <label><StudentSystemText k="currentPassword" /><input type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} autoComplete="current-password" /></label>
            <label><StudentSystemText k="newPassword" /><input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} autoComplete="new-password" maxLength={100} /></label>
            <label><StudentSystemText k="confirmPassword" /><input type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} autoComplete="new-password" maxLength={100} /></label>
            <p className="sa-settings__hint"><StudentSystemText k="passwordRule" /></p>
            {passwordError === "required" && <p className="sa-settings__error" role="alert"><StudentSystemText k="passwordRequired" /></p>}
            {passwordError === "mismatch" && <p className="sa-settings__error" role="alert"><StudentSystemText k="passwordMismatch" /></p>}
            {error && !passwordError && <p className="sa-settings__error" role="alert">{error}</p>}
            <div className="sa-settings__actions">
              <button className="sa-button sa-button--primary sa-button--default" type="submit" disabled={isSaving}>
                <StudentIcon name="lock" size={18} role="decorative" />
                <span><StudentSystemText k={isSaving ? "saving" : "changePassword"} withinControl /></span>
              </button>
            </div>
          </form>
        </StudentSection>
      </div>
    </StudentPage>
  );
}

