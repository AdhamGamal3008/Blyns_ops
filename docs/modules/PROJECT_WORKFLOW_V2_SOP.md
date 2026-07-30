# **Bovali Studio — Project Delivery Workflow**

**Standard Operating Procedure · Version 2.0** Effective: \[DATE\] · Owner: Head of Product · Supersedes: v1.0 (16-stage flow)

---

## **1\. Why this changed**

Version 1.0 ran **16 stages, 12 approver roles, and 13 blocking gates**. Eight of those stages carried no gate and no unique control — they existed to be clicked through. The result was a workflow where most elapsed time was spent waiting for sign-off rather than doing work, and where technical checks were being rushed because they blocked crews already standing on site.

Version 2.0 keeps every check that protects a warranty, prevents rework, or defends a claim. It removes the ceremony around them.

|  | v1.0 | v2.0 |
| ----- | ----- | ----- |
| Stages | 16 | 9 |
| Approver roles | 12 | 6 |
| Blocking gates | 13 | 5 |
| Entry documents | 9 | 3 |

**Nothing technical was deleted.** Checks that used to block now log. The data is still captured — it just no longer holds up a crew.

---

## **2\. Approval authority**

Six roles hold approval authority. Nobody else can advance a stage.

| Role | Approves | Accountable for |
| ----- | ----- | ----- |
| `project_director` | Stage 1, Stage 9 | Commercial commitment in, client acceptance out |
| `design_manager` | Stage 3 | The design package is buildable and specified |
| `engineering` | Stage 4 | Measurements are correct at design freeze |
| `procurement_manager` | Stage 5 | BOM is complete and stock is reserved |
| `production_manager` | Stage 6 | Goods leave the factory correct, protected, and scheduled |
| `project_manager` | Stage 7, Stage 8 | Site is fit to receive, and install is executed to spec |

**Delegation:** an approver may delegate to a named deputy in writing for a defined period. Approvals are never delegated verbally and never delegated to the person who executed the work.

---

## **3\. The five hard gates**

A hard gate **blocks progression**. It cannot be waived by the stage approver — only by the `project_director`, in writing, with the reason recorded against the project.

| \# | Stage | Gate | Why it is non-negotiable |
| ----- | ----- | ----- | ----- |
| G1 | 4 · Measurement Verification | Deviation ≤ 3mm (severe \> 6mm) | Point of no return. Material is cut after this. An error here is scrapped stock, not a revision. |
| G2 | 5 · Material Procurement | `bom_present` | Reserves stock in Inventory. Without it, stock is double-promised across projects. |
| G3 | 7 · Site Readiness | Concrete RH per ASTM F2170 | Warranty-bearing and third-party defensible. Moisture failures are our single largest claim category. |
| G4 | 7 · Site Readiness | Subfloor flatness | The \#1 cause of rework. Cheaper to fix before install by an order of magnitude. |
| G5 | 8 · Installation | Timber moisture content | Warranty-bearing. Determines whether we honour or void a claim 18 months out. |

### **Logged, not blocking**

The following were gates in v1.0. They are now **recorded fields** — mandatory to fill, but they do not stop work:

| Check | Now captured at | Why it was demoted |
| ----- | ----- | ----- |
| Substrate soundness (survey) | Stage 2 findings register | Duplicate of the Stage 7 check. Site conditions change between survey and install; the Stage 7 reading is the one that counts. |
| Ambient RH during install | Stage 8 daily log | As a gate it invited falsification, because it blocked a crew mid-work. As a passive daily log it is honest data we can use in a dispute. |
| Channel alignment | Stage 9 snag list | Workmanship criterion, not a readiness condition. |
| 3mm reveal | Stage 9 snag list | Same. Assessed on the finished surface, not mid-install. |

---

## **4\. The nine stages**

### **Stage 1 · Project Initiation**

**Owner:** Sales / Project Coordinator · **Approves:** `project_director` *Consolidates v1.0 Stages 1 and 2\.*

**Entry documents — 3 required:**

1. Signed LOI or Purchase Order  
2. Approved scope / BOQ  
3. Site access confirmation

Everything else (client brand guidelines, prior drawings, warranty schedules, site photos, insurance certificates, contact matrix) attaches to the project when available and does not hold up initiation.

**Tasks:** create project record · assign core team · log client requirements · confirm commercial terms

**Output:** live project with a director-approved commercial baseline.

---

### **Stage 2 · Site Survey & Technical Assessment**

**Owner:** Engineering · **Approves:** *no separate approval — auto-advances on completion* *Was v1.0 Stage 3\.*

This stage no longer carries an approval or a gate. Its output feeds the design package, and `design_manager` accepts it implicitly when approving Stage 3\.

**Tasks:** dimensional survey · substrate observation · services and level check · access and logistics assessment

**Findings register (record, do not gate):** substrate soundness, existing damage, level variance, access constraints, anything that could affect material choice.

**Output:** survey report attached to the project.

---

### **Stage 3 · Design Package**

**Owner:** Design · **Approves:** `design_manager` *Consolidates v1.0 Stages 4, 5 and 6\.*

Concept, material selection and shop drawings are now approved as **one package by one authority**. Procurement provides cost and lead-time input into this stage but does not approve it — a material that is unavailable or over budget is a design problem to resolve before sign-off, not a second queue afterwards.

**Tasks:** concept design · material selection (with procurement lead-time input) · specification · shop drawings

**Output:** an approved, costed, buildable design package.

---

### **Stage 4 · Measurement Verification & Design Freeze**

**Owner:** Engineering · **Approves:** `engineering` · **GATE G1** *Was v1.0 Stage 7\. Unchanged — this is the most important control in the system.*

**Entry documents — 2 required:** approved shop drawings · as-built site measurements

**Gate:** deviation within tolerance — **≤ 3mm acceptable, \> 6mm severe**. A severe deviation returns the project to Stage 3 for redesign. It does not proceed on a verbal assurance.

**Output:** frozen design. After this point, any change is a Variation Order, not a revision.

---

### **Stage 5 · Material Procurement**

**Owner:** Procurement · **Approves:** `procurement_manager` · **GATE G2** *Was v1.0 Stage 8\. Unchanged.*

**Gate:** `bom_present` — approval reserves BOM stock via Inventory.

**Tasks:** finalise BOM · confirm supplier lead times · raise POs · reserve stock · confirm delivery window to factory

**Output:** materials committed and reserved against this project.

---

### **Stage 6 · Factory Release**

**Owner:** Production · **Approves:** `production_manager` *Consolidates v1.0 Stages 9, 10, 11 and 12\.*

Four sequential internal approvals became one release decision. Production, QC, packing and delivery planning are now **checklists within this stage**, all completed before the single release approval.

**Checklist — all four sections must be complete before release:**

* **Production:** manufactured to approved shop drawings  
* **Quality control:** dimensional check, finish check, batch/colour consistency  
* **Packing & protection:** edge protection, moisture barrier, labelling, handling instructions  
* **Delivery planning:** route, vehicle, offload method, site delivery window confirmed with the PM

**Output:** goods released, protected, and scheduled to site.

> **Note for the pilot:** this consolidation assumes factory and warehouse sit under one accountable manager. If packing damage or delivery scheduling proves to be a recurring failure point, split packing or delivery back out as a separate approval. Review at the first quarterly checkpoint.

---

### **Stage 7 · Site Readiness Inspection**

**Owner:** Project Manager · **Approves:** `project_manager` · **GATES G3, G4** *Was v1.0 Stage 13\.*

**No crew mobilises before this stage is approved.** A failed site readiness inspection is a client conversation, not a reason to start anyway.

**Gates:**

* **G3 — Concrete relative humidity**, tested per **ASTM F2170** (in-situ probe, not surface). Record probe locations, depth, equilibration time, and readings.  
* **G4 — Subfloor flatness**, measured against the project tolerance.

**Also recorded (not gating):** substrate soundness, ambient conditions, power and access availability, storage area.

**Output:** site accepted for installation, or a written remediation list issued to the client with a revised date.

---

### **Stage 8 · Installation**

**Owner:** Site Supervisor · **Approves:** `project_manager` · **GATE G5** *Was v1.0 Stage 14, reduced from 4 gates to 1\.*

**Gate:** **G5 — Timber moisture content** verified before laying begins.

**Daily log (record, do not gate):** ambient RH and temperature, crew on site, area completed, incidents or deviations.

Channel alignment and the 3mm reveal are **no longer install-stage gates**. They are assessed on the finished surface at Stage 9 and raised as snags.

**Output:** installation complete, daily log closed.

---

### **Stage 9 · Final Inspection & Client Handover**

**Owner:** Project Manager → Project Director · **Approves:** `project_director` *Consolidates v1.0 Stages 15 and 16\.*

**Inspection — snag list assessed on the finished surface:**

* Channel alignment  
* 3mm reveal  
* Finish consistency and colour match  
* Edge and junction detailing  
* Client-specific criteria from Stage 1

Snags are closed before handover. An open snag does not proceed to handover without written client acceptance.

**Handover pack — built automatically on approval:**

* As-built drawings  
* Material specifications and batch records  
* Warranty documentation  
* Care and maintenance instructions  
* Gate records G1–G5 (the technical defence file)  
* Site readiness and installation logs  
* Sign-off certificate

**Output:** client acceptance and a complete warranty defence file.

---

## 

---

## **6\. Mapping from v1.0**

For anyone cross-referencing the old flow:

| v1.0 Stage | v2.0 Stage |
| ----- | ----- |
| 1 Lead Conversion & Project Creation | 1 Project Initiation |
| 2 Requirements Collection | 1 Project Initiation |
| 3 Site Survey | 2 Site Survey & Technical Assessment |
| 4 Concept Design | 3 Design Package |
| 5 Material Selection | 3 Design Package |
| 6 Shop Drawings | 3 Design Package |
| 7 Site Measurement Verification | 4 Measurement Verification & Design Freeze |
| 8 Material Procurement | 5 Material Procurement |
| 9 Factory Production | 6 Factory Release |
| 10 Factory Quality Control | 6 Factory Release |
| 11 Packing & Protection | 6 Factory Release |
| 12 Delivery Planning | 6 Factory Release |
| 13 Site Readiness Inspection | 7 Site Readiness Inspection |
| 14 Installation | 8 Installation |
| 15 Final Quality Inspection | 9 Final Inspection & Client Handover |
| 16 Client Handover | 9 Final Inspection & Client Handover |

---

## **7\. Review**

This SOP is reviewed at the first quarterly checkpoint after rollout. Two items are explicitly open for reassessment:

1. Whether the Stage 6 consolidation holds, or whether packing/delivery needs to split back out.  
2. Whether the demoted checks (substrate soundness at survey, ambient RH, alignment, reveal) are still being captured reliably now that they no longer block.

Raise workflow issues to the Head of Product.

