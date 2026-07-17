// Settings module UI (docs/modules/SETTINGS.md): the client-side control
// panel. Sections map 1:1 to the spec's §1.1–1.6 + the approver map.

import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import type { ClientMe } from "../../shared/types";
import { ApproversSection } from "./ApproversSection";
import { EmployeesSection } from "./EmployeesSection";
import { EventsSection } from "./EventsSection";
import { InfoSection } from "./InfoSection";
import { ProfileSection } from "./ProfileSection";
import { RolesSection } from "./RolesSection";

const SECTIONS = [
  { key: "profile", label: "Company profile" },
  { key: "employees", label: "Employees" },
  { key: "roles", label: "Roles" },
  { key: "events", label: "Calendar events" },
  { key: "approvers", label: "Approvers" },
  { key: "info", label: "Security & modules" },
] as const;

export function SettingsPage() {
  const me = useOutletContext<ClientMe>();
  const [section, setSection] = useState<string>("profile");
  const canWrite = (me.role.permissions["settings"] ?? 0) >= 3;

  return (
    <>
      <div className="quick-actions">
        {SECTIONS.map((s) => (
          <button key={s.key}
            className={`btn ${section === s.key ? "btn-primary" : "btn-ghost"}`}
            onClick={() => setSection(s.key)}>
            {s.label}
          </button>
        ))}
      </div>
      {section === "profile" && <ProfileSection canWrite={canWrite} />}
      {section === "employees" && <EmployeesSection canWrite={canWrite} />}
      {section === "roles" && <RolesSection canWrite={canWrite} />}
      {section === "events" && <EventsSection canWrite={canWrite} />}
      {section === "approvers" && <ApproversSection canWrite={canWrite} />}
      {section === "info" && <InfoSection />}
    </>
  );
}
