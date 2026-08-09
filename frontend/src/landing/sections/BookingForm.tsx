// The discovery-session request form — the landing page's one functional feature.
// Posts to the public endpoint (no auth), then swaps to a confirmation. Required
// fields use native validation; a hidden honeypot catches bots (dropped
// server-side). Reskinned for the dark landing with native controls — the submit
// path, honeypot, and payload are unchanged.

import { type FormEvent, useState } from "react";
import { errorText } from "../../shared/ui";
import { submitBooking } from "../api";
import styles from "./BookingForm.module.css";

const INDUSTRY_OPTIONS = [
  { value: "", label: "Select your field…" },
  { value: "interior_fit_out", label: "Interior Fit-Out" },
  { value: "flooring", label: "Flooring" },
  { value: "wall_cladding", label: "Wall Cladding" },
  { value: "custom_furniture", label: "Custom Furniture" },
  { value: "general_contractor", label: "General Contractor" },
  { value: "other", label: "Other" },
];

const SIZE_OPTIONS = [
  { value: "", label: "Optional" },
  { value: "1-10", label: "1–10" },
  { value: "11-50", label: "11–50" },
  { value: "51-200", label: "51–200" },
  { value: "201-500", label: "201–500" },
  { value: "500+", label: "500+" },
];

type Status = "idle" | "submitting" | "done";

export function BookingForm() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState("");
  const [phone, setPhone] = useState("");
  const [industry, setIndustry] = useState("");
  const [size, setSize] = useState("");
  const [preferred, setPreferred] = useState("");
  const [message, setMessage] = useState("");
  const [website, setWebsite] = useState(""); // honeypot
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<unknown>(null);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setStatus("submitting");
    try {
      await submitBooking({
        full_name: fullName.trim(),
        work_email: email.trim(),
        company: company.trim(),
        industry,
        phone: phone.trim() || undefined,
        company_size: size || undefined,
        preferred_at: preferred || undefined,
        message: message.trim() || undefined,
        website,
      });
      setStatus("done");
    } catch (err) {
      setError(err);
      setStatus("idle");
    }
  }

  if (status === "done") {
    return (
      <div className={styles.done} role="status">
        <p className={styles.doneTitle}>Your request is in.</p>
        <p className={styles.doneBody}>
          Thank you — we&rsquo;ll be in touch shortly to confirm your discovery session.
        </p>
      </div>
    );
  }

  return (
    <form className={styles.form} onSubmit={submit}>
      <div className={styles.grid}>
        <label className={styles.field}>
          <span className={styles.label}>Full name <em>*</em></span>
          <input className={styles.input} value={fullName} onChange={(e) => setFullName(e.target.value)}
            autoComplete="name" required />
        </label>
        <label className={styles.field}>
          <span className={styles.label}>Work email <em>*</em></span>
          <input className={styles.input} type="email" value={email} onChange={(e) => setEmail(e.target.value)}
            autoComplete="email" required />
        </label>
        <label className={styles.field}>
          <span className={styles.label}>Company <em>*</em></span>
          <input className={styles.input} value={company} onChange={(e) => setCompany(e.target.value)}
            autoComplete="organization" required />
        </label>
        <label className={styles.field}>
          <span className={styles.label}>Phone</span>
          <input className={styles.input} type="tel" value={phone} onChange={(e) => setPhone(e.target.value)}
            autoComplete="tel" />
        </label>
        <label className={styles.field}>
          <span className={styles.label}>Your field <em>*</em></span>
          <select className={styles.select} value={industry} onChange={(e) => setIndustry(e.target.value)} required>
            {INDUSTRY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value} disabled={o.value === ""}>{o.label}</option>
            ))}
          </select>
        </label>
        <label className={styles.field}>
          <span className={styles.label}>Company size</span>
          <select className={styles.select} value={size} onChange={(e) => setSize(e.target.value)}>
            {SIZE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </label>
      </div>

      <label className={styles.field}>
        <span className={styles.label}>Preferred date &amp; time</span>
        <input className={styles.input} type="datetime-local" value={preferred}
          onChange={(e) => setPreferred(e.target.value)} />
        <span className={styles.hint}>Optional — we&rsquo;ll confirm a slot that works.</span>
      </label>

      <label className={styles.field}>
        <span className={styles.label}>Anything we should know?</span>
        <textarea className={styles.textarea} rows={3} value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="A sentence on your projects, teams, or the challenge you're solving." />
      </label>

      {/* Honeypot — off-screen, not focusable; a real user never fills it. */}
      <div className={styles.hp} aria-hidden="true">
        <label>
          Website
          <input tabIndex={-1} autoComplete="off" value={website}
            onChange={(e) => setWebsite(e.target.value)} />
        </label>
      </div>

      {error != null && (
        <p className={styles.error} role="alert">{errorText(error)}</p>
      )}

      <button type="submit" className={styles.submit} disabled={status === "submitting"}>
        {status === "submitting" ? "Sending…" : "Book my discovery session"}
      </button>
      <p className={styles.fineprint}>We&rsquo;ll only use your details to arrange your session.</p>
    </form>
  );
}
