# Abby ISO/IEC 42001 AI Management System Alignment Plan

**Document owner:** To be assigned by top management  
**Approver:** To be assigned by top management  
**Version:** 0.1-draft  
**Draft date:** 2026-07-25  
**Review cadence:** Quarterly and after any material AI-system change  
**Reference standard:** ISO/IEC 42001:2023

## 1. Purpose and status

This plan defines a practical route for aligning Abby's development, provision, and use of artificial intelligence with ISO/IEC 42001:2023. It covers the management-system requirements in Clauses 4–10 and the reference controls in Annex A.

This is an implementation plan, not a declaration of conformity or certification. Conformity requires implemented and effective processes, retained evidence, management approval, internal audit, management review, and—if certification is sought—assessment by an accredited certification body. Repository artifacts can support the AI management system (AIMS), but organizational actions and records outside the repository are also required.

The plan is based on:

- review of the supplied `ISO42001.pdf`;
- review of Abby's source, tests, architecture, product, validation, and development-plan documentation as of 2026-07-25;
- Abby's role as a developer/provider of AI-enabled scientific software and as a user of third-party AI systems and AI-assisted development tools.

## 2. Proposed AIMS scope

### 2.1 Scope statement

The proposed AIMS covers the design, development, validation, deployment, operation, monitoring, support, change, and retirement of Abby capabilities that use AI or materially support AI outputs, including associated data, models, scientific tooling, APIs, workers, user interfaces, and development automation.

In scope:

1. **Affinity prediction and scientific decision support**
   - Deterministic baseline affinity scoring and consensus outputs.
   - Learned structure-model inference, including DeepFRI/ProteinMPNN-style integration paths.
   - Calibration, confidence, out-of-distribution, and explainability outputs.
2. **AI-adjacent structure interpretation**
   - CDR annotation and quality calibration.
   - Structure-derived graph and descriptor generation that feeds learned models.
   - Imported AlphaFold 3, Boltz-1, Rosetta, and other externally generated structure artifacts.
3. **Optional simulation-backed workflows**
   - Gromacs-CIF execution and imported trajectory summaries when used to influence model inputs or outputs.
4. **Data and evidence lifecycle**
   - Uploaded structures, validation corpora, training/evaluation data, model artifacts, provenance, event records, and exported prediction artifacts.
5. **AI used to develop or maintain Abby**
   - GitHub Copilot or other generative-AI coding assistance.
   - Agentic/self-healing development automation that can propose or apply changes.
   - AI-assisted documentation, testing, review, or issue triage.
6. **Third parties and infrastructure**
   - External model providers, scientific libraries, hosted services, object storage, and other suppliers that affect AI-system behavior or evidence.

Initially out of scope unless later brought into production:

- Independent research notebooks or experiments that cannot affect Abby releases, production data, or user outputs.
- General-purpose office AI use with no Abby source, data, model, customer, or operational access.

Exclusions must be documented and justified in the AIMS scope and Statement of Applicability (SoA), not assumed.

### 2.2 Intended use and prohibited use

Abby should be formally described as **research and engineering decision support**, not an autonomous clinical, diagnostic, therapeutic, regulatory, or safety-critical decision-maker. A qualified human remains accountable for interpreting outputs and deciding whether to act on them.

Document and enforce at least these use boundaries:

- Do not represent affinity estimates, generated structures, CDR annotations, or simulation summaries as experimentally verified facts.
- Do not use Abby outputs as the sole basis for clinical diagnosis, treatment, patient selection, or safety-critical decisions.
- Do not suppress uncertainty, provenance, validation warnings, stub/fallback status, or known limitations.
- Do not use customer or confidential structures for model training or external AI services without explicit authorization and a documented lawful basis.
- Do not permit autonomous AI agents to merge, deploy, alter compliance evidence, weaken quality gates, or expose secrets without authorized human review.

## 3. Organizational context and interested parties

The AIMS owner must maintain a context register addressing ISO/IEC 42001 Clauses 4.1–4.4.

### 3.1 Relevant roles

Abby currently performs or can perform these roles:

- AI producer/developer, tester, evaluator, deployer, and operator;
- AI product/service provider;
- AI user of third-party models and development assistants;
- system integrator of scientific and AI components;
- data acquirer/curator for validation and potential training data;
- customer-facing provider of scientific decision-support outputs.

### 3.2 Interested parties and likely needs

| Interested party | Relevant needs and expectations |
| --- | --- |
| Researchers and product users | Validated performance, uncertainty, traceability, clear limitations, reproducibility, support, and incident notification |
| Structure/data owners | Confidentiality, authorized use, retention/deletion controls, provenance, and no unapproved training or third-party disclosure |
| Domain experts | Scientifically defensible assumptions, representative evaluation, interpretable outputs, and human override |
| Developers and operators | Approved tools, secure access, reproducible environments, clear release criteria, event logs, and incident runbooks |
| Management/governing body | Defined risk appetite, measurable objectives, resource needs, performance reports, and accepted residual risk |
| Suppliers/model providers | Allocated responsibilities, integration requirements, security and quality expectations, and corrective-action channels |
| Regulators/auditors/certification bodies | Scope, legal register, impact/risk records, SoA, evidence of effective controls, audits, reviews, and corrective actions |
| Potentially affected individuals and society | Protection from misleading scientific claims, privacy/security harms, unsafe downstream reliance, bias, and excessive environmental impact |

### 3.3 Context issues to document

- Jurisdictions in which Abby is developed, hosted, sold, and used.
- Applicable AI, privacy, cybersecurity, intellectual-property, export, research, and sector-specific requirements.
- Contractual obligations for customer structures and generated artifacts.
- Scientific limitations and domain shift across antibodies, VHHs, aptamers, conjugates, and other structures.
- Dependence on optional or externally supplied models and tools.
- Environmental impact of learned-model and molecular-dynamics workloads; record the determination required by Clause 4.1 regarding climate change relevance.

## 4. Current-state assessment

### 4.1 Existing strengths and reusable evidence

| Existing control/evidence | Repository evidence | ISO/IEC 42001 relevance |
| --- | --- | --- |
| Typed model, simulation, CDR, structure-generation, dataset, and artifact provenance | `src/abby_api/schemas/common.py`, `src/abby_api/services/predictions.py` | A.4, A.6.2.3, A.6.2.7, A.7.5, A.8.2 |
| Deterministic baseline scoring and explicit learned-model integration | `src/abby_api/services/baseline_models.py`, `src/abby_api/services/graph_models.py` | A.6.1, A.6.2 |
| Dataset licensing, attribution, and source validation | `src/abby_api/services/dataset_governance.py`, `tests/test_dataset_governance.py` | A.4.3, A.7.2–A.7.5, A.10.3 |
| Canonical structure regression corpus and validation harness | `validation_dataset/ANDD_pdb/`, `src/abby_api/validation_harness.py`, `tests/test_validation_harness.py` | A.6.2.4, A.7.4 |
| Determinism, provenance, structure-flow, batch, simulation, and learned-model tests | `tests/` | A.6.2.4–A.6.2.6 |
| CDR calibration and drift-warning controls | `src/abby_api/services/cdr_quality_calibration.py`, `src/abby_api/services/cdr_annotation.py`, `tests/test_cdr_quality_calibration.py` | A.6.2.4, A.6.2.6 |
| Health and optional-dependency visibility | `src/abby_api/services/system.py`, `tests/test_health.py` | A.4.4–A.4.5, A.6.2.6 |
| Versioned API and frontend contracts | `OpenAPI_Abby_v1.yaml`, `src/abby_api/schemas/`, `frontend/src/types/api.ts` | A.6.2.2, A.6.2.7, A.8.2 |
| CI test/lint/build gates and bounded self-healing behavior | `.github/workflows/`, `.github/scripts/self_heal_ci.sh`, `.github/copilot-instructions.md` | A.6.1.3, A.6.2.4–A.6.2.5 |
| mmCIF-first chemistry-preservation policy and tests | `.github/copilot-instructions.md`, `src/abby_api/services/structure_parsing.py`, `tests/test_structure_flow.py` | A.6.2.2–A.6.2.4 |

These artifacts are useful evidence, but technical implementation alone does not satisfy management-system requirements.

### 4.2 Principal gaps

1. No approved AIMS scope, AI policy, objectives, governance charter, or assigned accountable owner.
2. No formal interested-party register or applicable-requirements/legal register.
3. No repeatable AI risk methodology, risk criteria, risk register, treatment plan, residual-risk approval, or SoA.
4. No formal AI system impact-assessment process covering intended use, foreseeable misuse, individuals, society, privacy, safety, and environmental impact.
5. No controlled AI system inventory with lifecycle status, criticality, owners, suppliers, data, models, and deployment locations.
6. No documented competence matrix, training records, awareness program, or communication plan.
7. Technical provenance exists, but request/user action logs, tamper evidence, retention, access, review, and incident correlation are incomplete.
8. No approved AI incident/concern reporting, investigation, external communication, nonconformity, or corrective-action process.
9. No formal model/data promotion, deployment, rollback, retirement, or material-change approval records.
10. Monitoring is fragmented; persistent production metrics, alert thresholds, review cadence, and effectiveness evaluation are not established.
11. No internal-audit program, management-review records, or continual-improvement register.
12. Third-party AI, scientific dependencies, and AI coding tools lack a unified supplier assessment and responsibility allocation process.
13. AI-assisted development has repository guardrails but lacks formal rules for approved data, secret handling, human review, output verification, attribution, and retained evidence.

## 5. Alignment principles

The implementation should follow these principles:

- **Risk proportionality:** apply stronger controls to learned predictions, externally generated structures, sensitive data, high-cost simulations, and any downstream health/safety reliance.
- **Human accountability:** AI may advise or automate bounded tasks; named people approve risk acceptance, releases, incidents, and consequential use.
- **Structure and evidence integrity:** preserve mmCIF relational chemistry, chain mapping, descriptor hashes, model/data versions, warnings, and artifacts.
- **Transparency:** expose intended use, limitations, confidence, fallback/stub status, provenance, and human-oversight requirements.
- **Reproducibility:** version code, configuration, datasets, preprocessing, models, seeds, environments, and evaluation results.
- **Data stewardship:** collect and retain only authorized data; record rights, provenance, quality, preparation, access, and disposal.
- **Secure-by-default AI use:** prevent secrets, confidential structures, customer data, and restricted code from being sent to unapproved AI services.
- **No silent degradation:** dependency fallbacks and model substitutions must be explicit, logged, tested, and reflected in outputs.
- **Continual improvement:** use incidents, concerns, audits, monitoring, user feedback, and scientific validation to drive corrective action.

## 6. Target AIMS document and evidence set

Create controlled documents and records under `Compliance/`. Policies and records can link to technical evidence elsewhere in the repository.

| Artifact | Minimum content | Owner/approval |
| --- | --- | --- |
| `AIMS_scope.md` | boundaries, locations, roles, AI systems, exclusions, context | AIMS owner / top management |
| `AI_policy.md` | responsible-AI principles, commitments, exceptions, review cadence | top management |
| `AI_objectives_and_metrics.md` | measurable objectives, targets, owners, resources, due dates, evaluation | top management |
| `Interested_parties_and_requirements.md` | parties, needs, legal/contractual requirements, communication obligations | compliance/legal owner |
| `AI_system_inventory.md` | system ID, owner, purpose, status, risk tier, models, data, suppliers, deployments, retirement | system owners |
| `AI_risk_methodology.md` | scales, acceptance criteria, impact/likelihood, review triggers, aggregation | risk owner |
| `AI_risk_register.md` | inherent/residual risk, controls, owner, treatment, due date, acceptance | risk owners / designated management |
| `AI_impact_assessment_template.md` | intended use/misuse, affected parties, harms/benefits, human oversight, jurisdictions | impact-assessment owner |
| `Statement_of_Applicability.md` | every Annex A control, applicability, justification, implementation, evidence, status | AIMS owner / management |
| `Data_governance_policy.md` | acquisition, rights, quality, representativeness, preparation, provenance, retention, deletion | data steward |
| `Model_and_system_lifecycle.md` | requirements, design, V&V, release, deployment, monitoring, rollback, retirement | engineering/ML owner |
| `AI_supplier_register.md` | provider, component, terms, version, risk, due diligence, responsibilities, monitoring, exit plan | supplier owner |
| `AI_assisted_development_policy.md` | approved tools/data, prohibited disclosures, review/testing, attribution, autonomy limits | engineering owner |
| `Human_oversight_and_user_transparency.md` | oversight points, override/stop authority, warnings, user information, limitations | product/domain owner |
| `AI_incident_and_concern_management.md` | intake, anonymity/confidentiality, triage, escalation, investigation, notification, lessons learned | incident owner |
| `Event_logging_and_retention.md` | logged events, minimization, access, integrity, review, retention/disposal | security/operations owner |
| `Competence_and_awareness.md` | role competencies, training, effectiveness checks, records | management/HR |
| `Communication_plan.md` | what/when/with whom/how, including incidents and authorities | communications/compliance owner |
| `Internal_audit_program.md` | scope, criteria, cadence, independence, reporting, follow-up | audit owner |
| `Management_review_template.md` | required inputs, decisions, actions, owners, due dates | top management |
| `Nonconformity_and_CAPA_register.md` | issue, containment, cause, correction, corrective action, effectiveness | AIMS owner |
| `Document_control.md` | identifiers, versions, approvals, access, retention, external documents | document-control owner |

## 7. Phased implementation roadmap

### Phase 0 — Sponsorship and boundaries (days 0–15)

**Objective:** establish authority and a controlled scope before creating disconnected paperwork.

Actions:

- Appoint the AIMS executive sponsor, AIMS manager, AI risk owner, data steward, security/privacy owner, domain-validation owner, model owner, incident owner, and internal-audit owner.
- Approve the scope in Section 2, organization roles, intended-use statement, and explicit exclusions.
- Identify deployment jurisdictions, applicable laws/contracts, and whether any customer data is personal, health-related, confidential, export-controlled, or otherwise restricted.
- Formally record whether climate change is relevant and how compute-intensive model/simulation workloads will be evaluated.
- Freeze a baseline inventory of active, optional, experimental, retired, and third-party AI systems.
- Establish document-control conventions: owner, approver, version, approval date, next review, classification, change history, retention, and evidence links.

Deliverables:

- Approved `AIMS_scope.md`.
- Approved governance/RACI section in `AI_policy.md` or a separate governance charter.
- Initial `Interested_parties_and_requirements.md`.
- Initial `AI_system_inventory.md`.
- Controlled-document template and register.

Exit criteria:

- Every in-scope AI system has an accountable owner and lifecycle status.
- Top management approves the scope and provides resources.
- Exclusions and organizational interfaces are explicit.

### Phase 1 — Policy, objectives, risk, impact, and SoA (days 15–45)

**Objective:** satisfy the core planning framework in Clauses 5 and 6.

Actions:

- Approve an AI policy aligned with security, privacy, quality, scientific integrity, open-source, and software-development policies.
- Define measurable objectives. Initial candidates:
  - 100% of production prediction results carry model, preprocessing, data, descriptor, warning, and artifact provenance where applicable.
  - 100% of production AI systems have approved intended use, limitations, risk assessment, and impact assessment before release.
  - 100% of material model/data changes meet documented V&V and approval gates.
  - 100% of high-severity AI incidents are triaged within the approved target and receive root-cause analysis.
  - 0 unauthorized transfers of customer/confidential data to external AI services.
  - Defined scientific performance and calibration thresholds are met by each promoted model and relevant data stratum.
- Define repeatable risk criteria and acceptance thresholds; distinguish organizational, individual, societal, scientific, security, privacy, safety, legal, and environmental impacts.
- Assess each inventory item, including foreseeable misuse and interactions between components.
- Perform an AI system impact assessment for the complete Abby service and separate assessments for materially different high-risk use cases or deployments.
- Select treatments, identify control owners and due dates, approve residual risk, and build the SoA against every Annex A control.

Minimum risks to assess:

- inaccurate or overconfident affinity predictions;
- use outside the validated domain, including clinical or safety-critical reliance;
- underrepresentation and performance variation across structure/molecule classes;
- loss or fabrication of mmCIF connectivity and structural semantics;
- hidden fallback/stub execution or unavailable dependencies;
- data leakage, model inversion/extraction, poisoning, malicious uploads, and prompt injection through AI-assisted tooling;
- provenance tampering or inability to reconstruct a prediction;
- third-party model/license/terms changes and supplier outages;
- model, data, concept, calibration, and dependency drift;
- autonomous agent changes that weaken tests, policies, or security controls;
- excessive compute cost or environmental impact;
- intellectual-property, privacy, confidentiality, and retention violations.

Deliverables:

- Approved `AI_policy.md` and `AI_objectives_and_metrics.md`.
- `AI_risk_methodology.md`, populated `AI_risk_register.md`, and treatment plan.
- Completed impact assessments.
- Approved `Statement_of_Applicability.md` with Annex A.2–A.10 coverage.

Exit criteria:

- Designated management approves treatment plans and residual risks.
- All Annex A controls are included or excluded with evidence-based justification.
- Objectives have owners, targets, resources, review dates, and measurement methods.

### Phase 2 — Operational controls and lifecycle evidence (days 30–90)

**Objective:** make responsible AI requirements enforceable in Abby's normal lifecycle.

#### 2.1 Requirements, design, and change control

- Add an AI change-impact section to issue/PR templates for model, dataset, feature, prompt/agent, dependency, schema, and intended-use changes.
- Define “material change” triggers: new model family, training/evaluation dataset, output meaning, intended use, deployment jurisdiction, supplier, autonomy level, privacy category, risk threshold, or significant performance shift.
- Require updated risk/impact assessments and approvals for material changes.
- Record architectural choices, model rationale, alternatives, security threats, human interaction, and known limitations.
- Prevent AI agents from approving their own changes; require independent human review and applicable CI gates.

#### 2.2 Data governance

- Inventory training, validation, test, calibration, production, uploaded, synthetic, and generated data.
- Extend existing `DatasetSourceProvenance` practices to record acquisition authority, permitted uses, source dates, transformations, labeling, quality, representativeness, known bias, retention, and disposal.
- Define quality thresholds by data purpose and molecule/structure strata.
- Separate customer uploads from approved training data; default to no training reuse.
- Establish deletion and legal-hold procedures and test restoration/deletion behavior.

#### 2.3 Verification, validation, and release

- Define release gates by risk tier and system type.
- Preserve current test gates and add model-specific acceptance criteria for scientific validity, calibration, robustness, domain coverage, reproducibility, security, privacy, and explainability.
- Generate a signed-off V&V report and model card for every promoted model bundle.
- Validate against representative holdouts and relevant strata; document failure rates and uncertainty rather than only aggregate performance.
- Maintain rollback and safe-disable procedures for learned models, simulation paths, external integrations, and agentic automation.
- Make stub/fallback behavior impossible to mistake for production model output.

#### 2.4 Deployment, operation, monitoring, and event records

- Define a production deployment checklist and evidence record.
- Persist structured event logs for use, model/version selection, key inputs or input references, output references, warnings, fallback paths, errors, human overrides, and material administrative changes.
- Avoid placing secrets, full sensitive structures, or unnecessary personal data in logs.
- Add integrity protection, access control, time synchronization, backup, retention, disposal, and periodic review.
- Define service and model metrics with thresholds, owners, alert paths, and response playbooks.
- Monitor model performance, calibration, OOD/fallback rates, per-stratum performance, dependency health, latency, failures, and resource consumption.
- Link request, worker, prediction, model, dataset, artifact, and incident identifiers.

#### 2.5 User transparency and human oversight

- Publish model/system cards that state purpose, intended users, validated domain, limitations, data summary, metrics, uncertainty, risks, required oversight, update history, and contact/reporting channels.
- Provide conspicuous user warnings for research-only status, uncertainty, fallback/stub execution, domain mismatch, and incomplete structure/connectivity.
- Define who can override, reject, stop, roll back, or quarantine outputs and systems.
- Verify through user testing that intended users can interpret outputs and warnings.

#### 2.6 AI-assisted software development

- Maintain an approved list of coding assistants, models, extensions, data-processing locations, and contractual terms.
- Classify source/data that may or may not be submitted to each tool; prohibit secrets, credentials, customer structures, unpublished datasets, and restricted material unless explicitly approved.
- Require human review, tests, security checks, licensing/IP review where relevant, and traceable authorship for AI-assisted changes.
- Preserve the repository's non-negotiable CI guardrails and prohibit agents from weakening controls to obtain passing results.
- Define maximum agent autonomy, allowed tools, sandbox boundaries, kill/rollback procedures, and supervision expectations.
- Log material agent actions and approvals without storing sensitive prompt content unnecessarily.

Deliverables:

- Approved lifecycle, data, supplier, human-oversight, AI-assisted-development, logging, and incident procedures.
- Model cards, dataset sheets, V&V reports, deployment records, and rollback exercises.
- Implemented persistent audit/event records and production monitoring.
- Tests covering critical control behavior.

Exit criteria:

- Each release can be reconstructed from approved requirements through deployment and operation.
- Every production output identifies relevant model/version, data/provenance, warnings, and fallback state.
- High-risk controls have operating evidence, not merely policy text.

### Phase 3 — Support, suppliers, incidents, and communications (days 60–120)

**Objective:** establish the people and ecosystem controls required by Clauses 7, 8, and Annex A.8–A.10.

Actions:

- Define competencies for AI governance, molecular modeling, ML validation, data stewardship, security/privacy, operations, impact assessment, and internal audit.
- Train personnel on the AI policy, intended-use limits, concern reporting, incident duties, secure AI-tool use, and consequences of nonconformity; evaluate training effectiveness.
- Create confidential concern-reporting and external adverse-impact channels with anti-retaliation expectations, qualified triage, escalation, and response targets.
- Define AI incident severity, containment, evidence preservation, root-cause analysis, regulatory/customer notification, recovery, and post-incident review.
- Inventory suppliers and document component purpose, version, license/terms, data flows, risk, service/support expectations, security/privacy posture, monitoring, corrective action, and exit strategy.
- Allocate responsibilities among Abby, customers, data providers, model providers, infrastructure providers, and integrators.
- Establish internal/external communication matrices, including what is reported to users, management, customers, suppliers, authorities, and auditors.

Deliverables:

- Competence matrix and training records.
- Concern and incident procedures plus exercise evidence.
- Supplier register, due-diligence records, responsibility matrix, and periodic review schedule.
- Communication plan and tested notification templates.

Exit criteria:

- Personnel can demonstrate awareness of policy and role-specific duties.
- At least one tabletop exercise tests an AI-output failure and one tests confidential-data exposure through an external AI tool.
- Critical suppliers have approved assessments and contingency plans.

### Phase 4 — Performance evaluation and certification readiness (days 120–180)

**Objective:** demonstrate that the AIMS operates effectively and improves.

Actions:

- Operate the control set long enough to accumulate representative records.
- Evaluate objective performance and control effectiveness on a defined cadence.
- Establish an internal-audit program covering Clauses 4–10 and the applicable SoA controls; ensure auditor objectivity and competence.
- Correct audit findings using documented containment, root cause, corrective action, owner, due date, and effectiveness review.
- Conduct management review with all Clause 9.3 inputs: prior actions, context changes, interested-party changes, nonconformities/CAPA, monitoring results, audits, and improvement opportunities.
- Record management decisions on resources, policy/objectives, scope, risks, controls, and improvement.
- Perform a certification-readiness assessment; remediate gaps before selecting an accredited certification body.

Deliverables:

- Monitoring/evaluation reports.
- Internal-audit plan, audit reports, findings, and closure evidence.
- Management-review minutes and action log.
- Updated SoA, risk register, impact assessments, and improvement register.
- Certification-readiness report.

Exit criteria:

- No overdue critical nonconformities or untreated unacceptable risks.
- Management confirms the AIMS is suitable, adequate, and effective.
- Evidence is controlled, retrievable, and internally consistent.

### Phase 5 — Continual improvement (ongoing)

Trigger review and potential reassessment after:

- a new AI model, dataset, supplier, intended use, user population, jurisdiction, or deployment environment;
- material performance/calibration drift or a changed scientific claim;
- a significant incident, complaint, adverse impact, security vulnerability, or privacy event;
- a major dependency, architecture, API, agent-autonomy, or data-flow change;
- legal, contractual, or standard changes;
- audit findings or management-review decisions.

Maintain a continual-improvement register that links each opportunity or nonconformity to action, owner, target date, verification, and closure evidence.

## 8. Annex A control implementation map

The final SoA must assess every control individually. The table below is the initial planning position, not the approved SoA.

| Annex A control | Initial state | Planned implementation/evidence |
| --- | --- | --- |
| A.2.2 AI policy | Gap | Approved `AI_policy.md` |
| A.2.3 Policy alignment | Gap | Crosswalk to security, privacy, quality, scientific integrity, HR, supplier, and SDLC policies |
| A.2.4 Policy review | Gap | Annual/triggered review records and management approval |
| A.3.2 Roles and responsibilities | Gap | Governance charter/RACI, job responsibilities, delegated authority |
| A.3.3 Reporting concerns | Gap | Confidential internal and external channels, triage and response records |
| A.4.2 Resource documentation | Partial | AI inventory and architecture/data-flow records |
| A.4.3 Data resources | Partial | Dataset provenance exists; add complete inventory, rights, quality, bias, retention, and use constraints |
| A.4.4 Tooling resources | Partial | Tool/model/dependency inventory with versions and intended purpose |
| A.4.5 System/computing resources | Partial | Environment, location, capacity, cost, resilience, and environmental-impact records |
| A.4.6 Human resources | Gap | Competence matrix, training and effectiveness records |
| A.5.2 Impact-assessment process | Gap | Approved process, triggers, method, reviewers, and integration with risk/change management |
| A.5.3 Impact-assessment records | Gap | Versioned assessments with retention and approval |
| A.5.4 Individual/group impacts | Gap | Privacy, fairness, accessibility, health/safety, financial, and human-rights analysis |
| A.5.5 Societal impacts | Gap | Scientific misuse, health/safety, environmental, economic, and misinformation/overclaiming analysis |
| A.6.1.2 Responsible-development objectives | Partial | Convert technical principles into approved measurable objectives |
| A.6.1.3 Responsible design/development | Partial | Existing plans/tests plus formal review, oversight, release, change, and approval procedures |
| A.6.2.2 Requirements/specification | Partial | Product/OpenAPI plans plus controlled AI requirements and material-change records |
| A.6.2.3 Design/development documentation | Partial | Architecture and provenance plus model/system cards and security-design records |
| A.6.2.4 Verification/validation | Strong partial | Existing tests/harnesses plus approved criteria, representative evaluation, and signed V&V reports |
| A.6.2.5 Deployment | Gap/partial | CI exists; add deployment plan, release sign-off, rollback, and environment evidence |
| A.6.2.6 Operation/monitoring | Partial | Health/drift features plus persistent metrics, alerts, review, support, and repair records |
| A.6.2.7 Technical documentation | Partial | Existing architecture/API docs plus audience-specific model/system cards and controlled updates |
| A.6.2.8 Event logs | Gap/partial | Provenance exists; add persistent use/admin/security records with integrity and retention controls |
| A.7.2 Development/enhancement data | Partial | Approved data-management lifecycle and separation of training/validation/test/production data |
| A.7.3 Data acquisition | Partial | Source provenance plus rights, selection rationale, quantity, characteristics, and approvals |
| A.7.4 Data quality | Partial | Validation corpus exists; add formal quality/representativeness thresholds and reports |
| A.7.5 Data provenance | Strong partial | Existing typed provenance plus lifecycle-wide transformations, verification, and integrity controls |
| A.7.6 Data preparation | Partial | Existing preprocessing/version fields plus controlled criteria, methods, rationale, and tests |
| A.8.2 User information | Partial | UI/API provenance exists; add intended use, AI notice, limitations, performance, oversight, and contact route |
| A.8.3 External reporting | Gap | Adverse-impact/concern reporting mechanism |
| A.8.4 Incident communication | Gap | Notification plan, legal/contractual matrix, templates, exercises |
| A.8.5 Interested-party reporting | Gap | Reporting-obligations register and evidence release process |
| A.9.2 Responsible use | Gap/partial | Intended-use boundaries plus user/employee procedures and AI-tool policy |
| A.9.3 Responsible-use objectives | Gap/partial | Measurable accountability, transparency, reliability, safety, privacy, security, and oversight objectives |
| A.9.4 Intended use | Partial | Product modes exist; add enforceable limits, monitoring, logs, and misuse response |
| A.10.2 Responsibility allocation | Gap | Supplier/customer responsibility matrix and contract clauses |
| A.10.3 Suppliers | Gap/partial | Dependency records exist; add risk-tiered due diligence, monitoring, correction, and exit plans |
| A.10.4 Customers | Gap | Customer-needs records, contractual expectations, use constraints, and feedback process |

## 9. Initial metrics and evidence dashboard

Management should approve targets after baseline measurement. Suggested measures:

| Measure | Suggested target | Evidence source |
| --- | --- | --- |
| Production AI systems with owner, risk tier, intended use, risk assessment, and impact assessment | 100% | AI inventory and assessment register |
| Annex A controls with approved applicability and current evidence | 100% | SoA |
| Material changes with risk/impact review and approval before release | 100% | PR/change and release records |
| Promoted models meeting all V&V criteria | 100% | V&V reports and CI artifacts |
| Outputs with required provenance and explicit fallback state | 100% | API/artifact sampling and automated tests |
| High-severity incidents triaged within target | 100% | Incident register |
| Corrective actions closed on time | At least 95%; 100% for critical items | CAPA register |
| Critical suppliers reviewed on schedule | 100% | Supplier register |
| In-scope personnel completing role-specific training | 100% | Training records |
| Unauthorized customer/confidential data transfers to AI tools | 0 | DLP/security events and incident records |
| Production performance/calibration reviewed on schedule | 100% | Monitoring review records |
| Internal audits and management reviews completed on schedule | 100% | Audit/review records |
| Compute/resource use for high-cost AI/MD jobs measured | 100% | Operational telemetry |

## 10. Priority repository work packages

These are the smallest practical implementation slices for Abby:

1. **Governance baseline:** create scope, policy, RACI, inventory, document control, and objectives.
2. **Risk baseline:** create methodology, risk register, impact assessment, treatment plan, and SoA.
3. **Lifecycle gate:** add controlled model/data/system cards and a release evidence template tied to current tests.
4. **Data controls:** extend dataset provenance into a complete data register with rights, quality, preparation, retention, and deletion.
5. **AI-development controls:** formalize Copilot/agent use, human review, confidential-data restrictions, autonomy limits, and evidence retention.
6. **Operational evidence:** implement persistent event/audit logging, correlation IDs, monitoring thresholds, alerting, and retention.
7. **Incident readiness:** create concern/incident/CAPA processes and run two tabletop exercises.
8. **Supplier controls:** assess external models, Gromacs-CIF, scientific libraries, hosting/storage, and AI development tools.
9. **Audit readiness:** run a full internal audit, close findings, and conduct management review.

For each work package, use testable acceptance criteria and link policy requirements to code/tests where automation is appropriate. Do not weaken existing mmCIF fidelity, provenance, test, lint, build, or CI integrity controls to accelerate compliance work.

## 11. Definition of alignment readiness

Abby is ready for an independent ISO/IEC 42001 conformity-readiness review when:

- the approved AIMS scope, policy, objectives, governance roles, and controlled-document process are active;
- the AI inventory, interested-party/legal register, risk assessments, impact assessments, treatment plans, and SoA are complete and current;
- applicable Annex A controls are implemented with operating evidence;
- personnel are competent and aware of their responsibilities;
- AI lifecycle, data, supplier, user-transparency, human-oversight, event-recording, and incident processes operate as documented;
- monitoring shows objectives and controls are evaluated for effectiveness;
- at least one complete internal-audit cycle and management review have occurred;
- nonconformities have documented correction, root-cause analysis, corrective action, and effectiveness checks;
- top management has accepted residual risks and authorized any certification assessment.

## 12. Immediate next action

Within 15 days, hold an AIMS initiation review to approve the proposed scope, appoint accountable roles, authorize resources, and assign owners for the first five controlled artifacts: `AIMS_scope.md`, `AI_policy.md`, `AI_system_inventory.md`, `Interested_parties_and_requirements.md`, and `AI_risk_methodology.md`. The risk register, impact assessment, treatment plan, and SoA should follow from those approved foundations rather than being drafted in isolation.
