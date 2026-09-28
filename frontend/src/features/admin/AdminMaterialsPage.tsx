import { useEffect, useState } from "react";
import Icon, { type UiIconName } from "../../shared/ui/Icon";
import StoryBuilderSection from "@features/teacher/components/story-builder/StoryBuilderSection";
import TeacherImageBuilderPage from "../teacher/TeacherImageBuilderPage";
import { canUseDatabase, listCustomStories } from "../../services/database";
import { useBulkAudioUpload } from "../teacher/components/story-builder/bulkAudioUpload";
import MaterialsImportDialog from "./MaterialsImportDialog";
import "../../shared/styles/MyStoriesPage.css";
import "../teacher/TeacherDashboardPage.css";
import "./AdminMaterialsPage.css";

export type AdminMaterialsTool = "builder" | "imageBuilder";

const MATERIALS_TOOLS: Array<{ id: AdminMaterialsTool; icon: UiIconName; title: string; blurb: string }> = [
  {
    id: "builder",
    icon: "library",
    title: "Story Builder",
    blurb: "Write a story, set its scenes, and publish it to students.",
  },
  {
    id: "imageBuilder",
    icon: "image",
    title: "AI Image Builder",
    blurb: "Generate and attach scene images for a story you have written.",
  },
];

export default function AdminMaterialsPage({ initialTool }: { initialTool?: AdminMaterialsTool } = {}) {
  const [tool, setTool] = useState<AdminMaterialsTool | null>(initialTool ?? null);
  const [importKind, setImportKind] = useState<"images" | "scripts" | null>(null);
  const [customStories, setCustomStories] = useState<any[]>([]);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!canUseDatabase()) return;
    listCustomStories().then(setCustomStories).catch(() => setError("Could not load saved stories for the audio uploader."));
  }, []);

  const { handleBulkUploadAudio, bulkAudioNotice, bulkAudioError, isBulkUploadingAudio } = useBulkAudioUpload(customStories, setCustomStories);

  if (tool) {
    return (
      <>
        <button type="button" className="tdash-back" onClick={() => setTool(null)}>
          Back to Materials
        </button>
        {tool === "builder" && <StoryBuilderSection showBulkAudio={false} />}
        {tool === "imageBuilder" && <TeacherImageBuilderPage />}
      </>
    );
  }

  return (
    <section className="tdash-card admin-materials-card">
      <div className="tdash-card-head">
        <div>
          <p className="stories-kicker">Content operations</p>
          <h2>Materials</h2>
        </div>
      </div>
      <p className="tdash-card-note">Keep the shared lesson assets together. Images and scripts update only existing stories from lessons 5–8.</p>
      <div className="admin-materials-upload-grid" aria-label="Bulk material uploads">
        <article className="admin-materials-upload-card">
          <Icon name="volume" size={20} />
          <h3>Upload audios</h3>
          <p>Use names like <code>5-1-02.mp3</code> for lesson 5-1, scene 2.</p>
          <label className="admin-upload-button">
            <Icon name="upload" size={16} />
            {isBulkUploadingAudio ? "Uploading…" : "Choose audio files"}
            <input
              type="file"
              hidden
              multiple
              accept="audio/*,.zip,application/zip,application/x-zip-compressed"
              disabled={isBulkUploadingAudio}
              aria-label="Upload audio files for lessons 5 to 8"
              onChange={(event) => { const files = Array.from(event.currentTarget.files ?? []); event.currentTarget.value = ""; if (files.length) void handleBulkUploadAudio(files); }}
            />
          </label>
          {(bulkAudioNotice || bulkAudioError) && <p className={bulkAudioError ? "admin-materials-error" : "admin-materials-notice"} role={bulkAudioError ? "alert" : "status"}>{bulkAudioError || bulkAudioNotice}</p>}
        </article>
        <article className="admin-materials-upload-card">
          <Icon name="image" size={20} />
          <h3>Upload images</h3>
          <p>One complete image per story: <code>5-1.png</code> through <code>8-3.png</code>.</p>
          <button type="button" className="admin-upload-button" onClick={() => { setError(""); setImportKind("images"); }}><Icon name="upload" size={16} /> Choose images</button>
        </article>
        <article className="admin-materials-upload-card">
          <Icon name="file" size={20} />
          <h3>Upload scripts</h3>
          <p>Import one CSV for all scenes with <code>lesson,story,scene,script</code>.</p>
          <button type="button" className="admin-upload-button" onClick={() => { setError(""); setImportKind("scripts"); }}><Icon name="upload" size={16} /> Choose CSV</button>
        </article>
      </div>
      {error && <p className="admin-materials-error" role="alert">{error}</p>}
      <div className="admin-materials-secondary">
        <h3>Authoring tools</h3>
        <p>Use these when you need to create a new story or generate artwork.</p>
      </div>
      <div className="tdash-tool-list">
        {MATERIALS_TOOLS.map((item) => (
          <button type="button" className="tdash-tool" key={item.id} onClick={() => setTool(item.id)}>
            <Icon name={item.icon} size={20} />
            <span>
              <strong>{item.title}</strong>
              <small>{item.blurb}</small>
            </span>
          </button>
        ))}
      </div>
      {importKind && <MaterialsImportDialog kind={importKind} onClose={() => setImportKind(null)} onConfirmed={(message) => { setNotice(message); setError(""); void listCustomStories().then(setCustomStories).catch(() => {}); }} />}
      {notice && <p className="admin-materials-notice" role="status">{notice}</p>}
    </section>
  );
}
