# ASTU CampusGuide AI — Knowledge Data Sources Catalog

## 1. Official ASTU Online Data Sources

CampusGuide AI retrieves official university knowledge from approved domain sources within `astu.edu.et` and `portal.astu.edu.et`.

| Source Title | Canonical URL | Type | Status | Chunks | Description & Evidence Covered |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **ASTU Homepage** | `https://www.astu.edu.et/` | Webpage | Candidate | 5 | Official university portal homepage. Covers university mission, orientation announcements, institutional collaborations, and research symposiums. |
| **Dean of Student Services** | `https://www.astu.edu.et/offices/administration-development/dean-of-student-services` | Webpage | Candidate | 2 | Official student life services: Cafeteria, Dormitory, Health Services Clinic, Guidance and Counseling, Sports, and Co-Curricular activities. |
| **Registrar and Alumni Executive** | `https://www.astu.edu.et/10-academics/212-registrar-and-alumni-executive` | Webpage | Candidate | 3 | Senate directives, admissions, registrations, student records, graduations, and official contact (Dr. Abebe Girma Regassa, Assistant Professor of Applied Mathematics). |
| **Active Calendars Portal** | `https://portal.astu.edu.et/pages/active_calendars` | Webpage | Candidate | 4 | Live official academic calendars (2026/2027 First Semester). Includes grade submission dates, continuous assessment schedules, final exam periods (January 2027), withdrawal, and readmission deadlines. |
| **Academic Calendar Hub** | `https://www.astu.edu.et/admission/importants/academic-calendar` | Webpage | Candidate | 1 | Hub page with historical links for 2026/2027 (2019 E.C.), 2025/2026, and 2023/2024 academic years. |
| **5th Research Symposium Abstract Template** | `.../Abstract_Template_5th_Internataional_Research_Symposium_ASTU_2025-Final_1.pdf` | PDF | Candidate | 5 | Academic paper formatting, manuscript submission guidelines, MS Word (.doc/.docx) instructions. |

---

## 2. Ingestion Statuses and OCR Handling

The ingestion pipeline (`backend/app/services/ingestion.py` and `extractors.py`) enforces strict quality checks:

1. **Candidate vs Verified Status**:
   - Webpages and documents automatically ingested from approved domains start in `candidate` status.
   - Only documents reviewed and verified by an authorized administrator transition to `verified` status.
   - The assistant never represents `candidate` documents as verified facts.
2. **Scanned Documents & OCR Detection**:
   - PDFs with fewer than 50 total characters or averaging fewer than 15 characters per page are flagged with `requires_ocr = true` and `chunk_count = 0`.
   - Examples from catalog: `notice.pdf`, `cde.pdf`, `Notice_New.pdf`, `Application_Form.pdf`.
   - These documents are withheld from vector search until OCR extraction is performed to prevent indexing empty or garbled content.

---

## 3. Knowledge Coverage Boundaries & Abstention Guidelines

- **Covered Topics**:
  - Core student services (cafeteria, dormitory, clinic, counseling, sports).
  - Registrar executive office and responsibilities.
  - Active academic calendar dates (grade submissions, exam schedules, withdrawal, readmission).
  - Official ASTU links and portals.
- **Unindexed Topics (Mandatory Abstention / Safe Referral)**:
  - International student tuition fees.
  - Department-specific course syllabus details and credit requirements.
  - Physical campus bookstore locations or unindexed departmental dean names.
  - For unindexed inquiries, CampusGuide AI explicitly acknowledges missing documentation and directs students to official ASTU portals (`https://www.astu.edu.et` or `https://portal.astu.edu.et`).
