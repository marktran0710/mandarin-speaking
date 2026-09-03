"use client";

import { useParams, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import ManagementApp, { type ManagementSection } from "../../../ManagementApp";

const SECTIONS: ManagementSection[] = ["stories", "quiz-review", "submissions", "support", "accounts", "analytics", "practice-debug"];

function isManagementSection(value: string | undefined): value is ManagementSection {
  return value !== undefined && SECTIONS.includes(value as ManagementSection);
}

function ManagementSectionContent() {
  const params = useParams<{ section?: string[] }>();
  const searchParams = useSearchParams();
  const sectionValue = Array.isArray(params?.section) ? params.section[0] : undefined;
  const section = isManagementSection(sectionValue) ? sectionValue : undefined;
  const roleParam = searchParams?.get("role");
  const initialRole = roleParam === "teacher" || roleParam === "admin" ? roleParam : undefined;

  if (!section) {
    return <main style={{ padding: 32 }}>Management area not found.</main>;
  }

  return <ManagementApp initialRole={initialRole} initialSection={section} />;
}

export default function ManagementSectionRoute() {
  return (
    <Suspense fallback={<main style={{ padding: 32 }}>Loading management portal…</main>}>
      <ManagementSectionContent />
    </Suspense>
  );
}
