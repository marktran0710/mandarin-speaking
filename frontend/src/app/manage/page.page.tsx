"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import ManagementApp from "../../ManagementApp";

function ManagementRouteContent() {
  const searchParams = useSearchParams();
  const roleParam = searchParams?.get("role");
  const initialRole = roleParam === "teacher" || roleParam === "admin" ? roleParam : undefined;
  return <ManagementApp initialRole={initialRole} />;
}

export default function ManagementRoute() {
  return (
    <Suspense fallback={<main style={{ padding: 32 }}>Loading management portal…</main>}>
      <ManagementRouteContent />
    </Suspense>
  );
}
