import os
import re
import tempfile
import streamlit as st

from Main import read_resume, extract_skills

# Import the function that extracts the Projects section.
from project_extraction import extract_project_section

from job_matching import (
    get_job_roles_from_database,
    calculate_job_match,
    get_match_description,
    get_improvement_suggestions,
    match_resume_with_description,
)

from database import (
    create_connection,
    save_job_description,
    save_job_description_result,
)


# ==================================================
# PAGE CONFIGURATION
# ==================================================

st.set_page_config(
    page_title="Resume Analyzer",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ==================================================
# SESSION STATE
# ==================================================

DEFAULTS = {
    "resume_skills": [],
    "resume_name": None,
    "resume_path": None,
    "resume_text": "",
    "resume_project_text": "",
    "career_results": [],
    "job_match_result": None,
    "job_match_saved": False,
    
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ==================================================
# STYLING
# ==================================================

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }

        .main-title {
            font-size: 36px;
            font-weight: 750;
            color: #5B5FEF;
        }

        .subtitle {
            color: #777888;
            font-size: 16px;
        }

        div[data-testid="stMetric"] {
            background-color: #F4F5FF;
            padding: 16px;
            border-radius: 12px;
            border: 1px solid #E7E8FF;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==================================================
# DATABASE HELPER
# FIND OR CREATE USER AND RESUME
# ==================================================

def get_or_create_user_and_resume(
    user_name,
    resume_name,
    resume_path,
):
    connection = create_connection()

    if connection is None:
        raise RuntimeError("Could not connect to MySQL.")

    cursor = None

    try:
        cursor = connection.cursor()

        # Reuse the first existing user with this name.
        cursor.execute(
            """
            SELECT id
            FROM users
            WHERE LOWER(TRIM(name)) = LOWER(TRIM(%s))
            ORDER BY id ASC
            LIMIT 1
            """,
            (user_name.strip(),),
        )

        row = cursor.fetchone()

        if row:
            user_id = row[0]
        else:
            cursor.execute(
                "INSERT INTO users (name) VALUES (%s)",
                (user_name.strip(),),
            )
            user_id = cursor.lastrowid

        # Reuse the same resume record when possible.
        cursor.execute(
            """
            SELECT id
            FROM resumes
            WHERE user_id = %s
              AND resume_name = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id, resume_name),
        )

        row = cursor.fetchone()

        if row:
            resume_id = row[0]
        else:
            cursor.execute(
                """
                INSERT INTO resumes
                    (user_id, resume_name, resume_path)
                VALUES (%s, %s, %s)
                """,
                (user_id, resume_name, resume_path),
            )
            resume_id = cursor.lastrowid

        connection.commit()

        return user_id, resume_id

    except Exception:
        connection.rollback()
        raise

    finally:
        if cursor is not None:
            cursor.close()

        connection.close()


# ==================================================
# SAVE JOB DESCRIPTION AND MATCH RESULT
# ==================================================

def save_job_match_to_mysql(
    user_name,
    resume_name,
    resume_path,
    job_description,
    match_percentage,
):
    user_id, resume_id = get_or_create_user_and_resume(
        user_name,
        resume_name,
        resume_path,
    )

    # Use the first non-empty line as the job title.
    lines = [
        line.strip()
        for line in job_description.splitlines()
        if line.strip()
    ]

    job_title = (
        lines[0][:250]
        if lines
        else "User-Provided Job Description"
    )

    # Reuse an identical description if already saved.
    connection = create_connection()

    if connection is None:
        raise RuntimeError("Could not connect to MySQL.")

    cursor = None

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT id
            FROM job_descriptions
            WHERE job_title = %s AND description = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (job_title, job_description),
        )

        row = cursor.fetchone()

        if row:
            job_description_id = row[0]
        else:
            job_description_id = save_job_description(
                job_title,
                job_description,
            )

        if not job_description_id:
            raise RuntimeError(
                "The job description could not be saved."
            )

    finally:
        if cursor is not None:
            cursor.close()

        connection.close()

    # Save the matching percentage and related IDs.
    saved = save_job_description_result(
        user_id,
        resume_id,
        job_description_id,
        match_percentage,
    )

    if not saved:
        raise RuntimeError(
            "The job match result could not be saved."
        )

    return True


# ==================================================
# PROJECT MATCHING HELPERS
# ==================================================

def _clean_project_line(line):
    """Clean bullet markers and PDF extraction artifacts from one line."""
    return re.sub(r"\s+", " ", str(line or "").replace("\\", " ")).strip().lstrip("•◦▪●*–—-\t ").strip()


def detect_skills_from_text(text):
    """Detect known skills from the complete resume or project description."""
    text = str(text or "")
    skill_patterns = {
        "Python": r"\bpython\b",
        "JavaScript": r"\bjavascript\b|\bjs\b",
        "HTML": r"\bhtml\s*5?\b",
        "CSS": r"\bcss\s*3?\b",
        "Angular": r"\bangular\b",
        "React": r"\breact(?:\.js)?\b",
        "TypeScript": r"\btypescript\b",
        "RESTful APIs": r"\brestful?\s+apis?\b|\brest\s+apis?\b|\brestful\s+api\s+integration\b",
        "Computer Vision": r"\bcomputer vision\b",
        "IoT": r"\biot\b|\binternet of things\b",
        "Raspberry Pi": r"\braspberry pi\b",
        "Arduino": r"\barduino\b",
        "Thermal Imaging": r"\bthermal imaging\b|\bthermal heat signatures?\b",
        "OpenCV": r"\bopencv\b",
        "Git": r"\bgit\b",
        "GitHub": r"\bgithub\b",
        "Flask": r"\bflask\b",
        "FastAPI": r"\bfast\s*api\b",
        "MySQL": r"\bmysql\b|\bmy\s+sql\b",
        "MongoDB": r"\bmongodb\b|\bmongo\s+db\b",
        "SQL": r"\bsql\b",
        "Bootstrap": r"\bbootstrap\b",
        "Tailwind CSS": r"\btailwind(?:\s+css)?\b",
        "Node.js": r"\bnode\.?js\b",
        "Responsive Web Design": r"\bresponsive\b",
        "Form Validation": r"\bform validation\b",
        "UI Development": r"\bui\b|\buser interface\b|\bfrontend\b|\bfront-end\b",
        "Debugging": r"\bdebug(?:ging|ged)?\b|\bdebug and resolve\b",
        "Problem-solving": r"\bproblem[- ]solving\b",
        "Docker": r"\bdocker\b",
        "Linux": r"\blinux\b",
        "Razorpay": r"\brazorpay\b",
        "REST APIs": r"\brest\s+apis?\b|\brestful\s+apis?\b",
    }
    found = []
    for skill, pattern in skill_patterns.items():
        if re.search(pattern, text, re.IGNORECASE):
            found.append(skill)
    # Avoid duplicate API labels; use the more descriptive canonical label.
    if "RESTful APIs" in found and "REST APIs" in found:
        found.remove("REST APIs")
    return found


def _skill_present(skill, text):
    """Alias-aware whole-word check used for matching project and job skills."""
    aliases = {
        "html": [r"\bhtml\s*5?\b"],
        "css": [r"\bcss\s*3?\b"],
        "javascript": [r"\bjavascript\b", r"\bjs\b"],
        "react": [r"\breact(?:\.js)?\b"],
        "angular": [r"\bangular\b"],
        "typescript": [r"\btypescript\b"],
        "restful apis": [r"\brestful?\s+apis?\b", r"\brest\s+apis?\b"],
        "git": [r"\bgit\b"],
        "github": [r"\bgithub\b"],
        "responsive web design": [r"\bresponsive\b"],
        "ui development": [r"\bui\b", r"\buser interface\b", r"\bfrontend\b", r"\bfront-end\b"],
        "debugging": [r"\bdebug(?:ging|ged)?\b", r"\bdebug and resolve\b"],
        "problem-solving": [r"\bproblem[- ]solving\b"],
        "node.js": [r"\bnode\.?js\b"],
        "tailwind css": [r"\btailwind(?:\s+css)?\b"],
        "mysql": [r"\bmysql\b", r"\bmy\s+sql\b"],
        "mongodb": [r"\bmongodb\b", r"\bmongo\s+db\b"],
        "fastapi": [r"\bfast\s*api\b"],
    }
    patterns = aliases.get(str(skill).lower(), [r"(?<![a-z0-9+#.])" + re.escape(str(skill).lower()) + r"(?![a-z0-9+#.])"])
    return any(re.search(pattern, str(text or ""), re.IGNORECASE) for pattern in patterns)


def extract_job_required_skills(job_description):
    """Return supported canonical skills explicitly mentioned in the job description."""
    detected = detect_skills_from_text(job_description)
    # A description can say "Angular or React"; both are requirements to check
    # against the resume because either framework may be relevant to the role.
    return list(dict.fromkeys(detected))


def split_project_entries(project_text):
    """Split project text into independent title/description records.

    Supports any project names. Blank lines are the preferred separator;
    a new bullet/title can also begin a new entry when blank lines are missing.
    """
    text = str(project_text or "").replace("\r", "\n").strip()
    if not text:
        return []

    # First use blank lines, which are the safest separator in the project editor.
    raw_blocks = [b.strip() for b in re.split(r"\n\s*\n+", text) if b.strip()]
    blocks = []
    for block in raw_blocks:
        lines = [_clean_project_line(line) for line in block.splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            continue
        title = lines[0].strip()
        description = " ".join(lines[1:]).strip()
        blocks.append({"title": title, "description": description})

    # If there are no blank lines, detect title-like lines without any known names.
    if len(blocks) <= 1:
        lines = [_clean_project_line(line) for line in text.splitlines()]
        lines = [line for line in lines if line]
        rebuilt = []
        current_title = None
        current_description = []
        action_start = re.compile(
            r"^(?:developed|built|designed|implemented|created|engineered|integrated|"
            r"trained|architected|leveraged|automated|analyzed|optimized|deployed|"
            r"constructed|provides|offers|features|uses|used|supports|created)\b",
            re.IGNORECASE,
        )
        for line in lines:
            is_title = (
                len(line.split()) <= 16
                and len(line) >= 8
                and not action_start.match(line)
                and not re.match(r"^(?:technical skills|experience|education|certifications?|"
                                 r"projects?|summary|professional summary)\b", line, re.I)
                and (":" in line or re.search(r"\b(?:system|application|platform|robot|engine|dashboard|"
                                              r"website|web app|management|analytics|booking|ordering)\b", line, re.I))
            )
            if is_title:
                if current_title:
                    rebuilt.append({"title": current_title, "description": " ".join(current_description).strip()})
                current_title, current_description = line, []
            elif current_title:
                current_description.append(line)
        if current_title:
            rebuilt.append({"title": current_title, "description": " ".join(current_description).strip()})
        if rebuilt:
            blocks = rebuilt

    # Remove section headings and duplicates while preserving order.
    excluded = re.compile(
        r"^(?:projects?|technical skills|developer tools|databases?\b|web technologies|"
        r"programming languages|core fundamentals|experience|work experience|education|"
        r"certifications?(?: and achievements)?|achievements|summary|professional summary)\s*:??$",
        re.IGNORECASE,
    )
    result, seen = [], set()
    for item in blocks:
        title = re.sub(r"\s+", " ", item["title"]).strip(" •◦▪●*-–—:")
        if not title or excluded.match(title):
            continue
        key = re.sub(r"\W+", " ", title.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        result.append(title + ("\n" + item["description"] if item["description"] else ""))
    return result[:30]

def extract_projects_from_resume(resume_text):
    """Extract project titles and reconnect descriptions without project-specific rules.

    Resume readers sometimes put all project titles in the Projects section and
    move the descriptions elsewhere in the extracted text. This function:
      1. Finds project titles from the Projects section.
      2. Builds sentence/paragraph chunks from the whole resume.
      3. Associates a description with a title only when meaningful title words
         occur in that description. It never assigns every nearby line blindly.

    Because arbitrary PDF layouts can lose reading order, the returned text is
    still editable for user review before matching.
    """
    source = str(resume_text or "")
    if not source.strip():
        return ""

    lines = [_clean_project_line(line) for line in source.splitlines()]
    lines = [line for line in lines if line]
    section_start = None
    section_end = len(lines)
    section_headings = {
        "experience", "work experience", "employment", "education", "technical skills",
        "skills", "certifications", "certifications and achievements", "achievements",
        "summary", "professional summary", "contact", "contact information", "internships",
    }
    for i, line in enumerate(lines):
        heading = re.sub(r"[^a-z ]", "", line.lower()).strip()
        if heading in {"projects", "project", "academic projects", "personal projects", "key projects"}:
            section_start = i + 1
            continue
        if section_start is not None and i >= section_start and heading in section_headings:
            section_end = i
            break

    # Extract titles from the Projects section. Descriptions are allowed in this
    # section too; title-like lines are separated from action-led description lines.
    titles = []
    if section_start is not None:
        for line in lines[section_start:section_end]:
            cleaned = _clean_project_line(line)
            if not cleaned:
                continue
            if re.match(
                r"^(?:developed|built|designed|implemented|created|engineered|integrated|"
                r"trained|architected|leveraged|automated|analyzed|optimized|deployed|"
                r"constructed|provides|offers|features|uses|used|supports)\b",
                cleaned, re.IGNORECASE,
            ):
                continue
            if len(cleaned.split()) >= 2 and len(cleaned) >= 6:
                titles.append(cleaned.strip(" •◦▪●*-–—:"))

    # Keep title-like lines unique and avoid accidental category labels.
    section_label = re.compile(
        r"^(?:technical skills|developer tools|databases?\b|web technologies|programming languages|"
        r"core fundamentals|machine learning|deep learning|data preprocessing|certifications|"
        r"education|experience|course college|coursework)\b", re.I,
    )
    unique_titles, seen = [], set()
    for title in titles:
        if section_label.match(title):
            continue
        key = re.sub(r"\W+", " ", title.lower()).strip()
        if key and key not in seen:
            seen.add(key)
            unique_titles.append(title)

    if not unique_titles:
        # No recognizable Projects section: leave the user's extracted section
        # as a fallback rather than guessing project names from unrelated text.
        return ""

    # Convert the full extracted text into candidate descriptive chunks. Merge
    # wrapped PDF lines, but start a new chunk at bullets or action-led sentences.
    chunks = []
    current = ""
    action_start = re.compile(
        r"^(?:developed|built|designed|implemented|created|engineered|integrated|trained|"
        r"architected|leveraged|automated|analyzed|optimized|deployed|constructed|"
        r"provides|offers|features|uses|used|supports|managed|performed|conducted|"
        r"worked|collaborated|consumed|maintained|configured|led|delivered|established)\b",
        re.I,
    )
    section_header = re.compile(
        r"^(?:technical skills|developer tools|databases?\s*&?\s*web frameworks|web technologies|"
        r"programming languages|core fundamentals|machine learning\s*&?\s*statistics|"
        r"deep learning\s*&?\s*vision|data preprocessing|experience|work experience|education|"
        r"projects?|certifications(?: and achievements)?|achievements|summary|professional summary)\s*:??$",
        re.I,
    )
    for raw_line in source.splitlines():
        raw = str(raw_line).strip()
        if not raw:
            if current:
                chunks.append(current.strip())
                current = ""
            continue
        # A standalone bullet marks a new paragraph in many PDF text extractions.
        if re.fullmatch(r"[•◦▪●*\-–—]+", raw):
            if current:
                chunks.append(current.strip())
                current = ""
            continue
        cleaned = _clean_project_line(raw)
        if not cleaned:
            continue
        if section_header.match(cleaned):
            if current:
                chunks.append(current.strip())
                current = ""
            continue
        starts_bullet = bool(re.match(r"^[•◦▪●*\-–—]\s*\S", raw))
        starts_action = bool(action_start.match(cleaned))
        if current and (starts_bullet or (starts_action and len(current.split()) >= 7)):
            chunks.append(current.strip())
            current = cleaned
        else:
            current = (current + " " + cleaned).strip() if current else cleaned
        # A sentence ending usually indicates a complete candidate paragraph.
        if current and re.search(r"[.!?]$", current):
            chunks.append(current.strip())
            current = ""
    if current:
        chunks.append(current.strip())

    # Remove exact title lines and obvious skill-category/certification content.
    title_keys = {re.sub(r"\W+", " ", t.lower()).strip() for t in unique_titles}
    excluded_chunk = re.compile(
        r"^(?:programming languages|core fundamentals|machine learning|deep learning|"
        r"data preprocessing|developer tools|databases?\s*&?\s*web frameworks|"
        r"web technologies|foundations of data science|hackerrank certifications|"
        r"python programming certification|virtual internship|successfully completed)\b",
        re.I,
    )
    chunks = [c for c in chunks if c and not excluded_chunk.match(c)]

    # Compare informative words from each title to each candidate description.
    # The same logic works with new project names; no project names are hard-coded.
    stop_words = {
        "project", "projects", "using", "with", "from", "into", "based", "system",
        "application", "platform", "solution", "powered", "developed", "built", "and",
        "the", "for", "using", "online", "web", "app", "engine", "management",
        "event", "events", "service", "services", "system", "data",
    }
    def content_words(text):
        return {
            token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9+#.]*", text)
            if len(token) >= 4 and token.lower() not in stop_words
        }

    # Build title-word sets, then assign each description chunk to at most one
    # project. This prevents the same line from appearing under multiple projects.
    title_word_map = {title: content_words(title) for title in unique_titles}
    assigned_chunks = {title: [] for title in unique_titles}
    for chunk in chunks:
        chunk_words = content_words(chunk)
        scores = {
            title: len(words.intersection(chunk_words))
            for title, words in title_word_map.items()
        }
        if not scores:
            continue
        best_score = max(scores.values())
        if best_score < 1:
            continue
        winners = [title for title, score in scores.items() if score == best_score]
        # If a sentence is equally related to multiple projects, do not guess.
        if len(winners) == 1 and len(chunk.split()) >= 5:
            assigned_chunks[winners[0]].append(chunk)

    project_records = []
    for title in unique_titles:
        description_parts = list(assigned_chunks.get(title, []))

        # If descriptions are physically nested below a title in the Projects
        # section, preserve those lines as well.
        try:
            title_position = next(
                i for i, line in enumerate(lines)
                if line.strip(" •◦▪●*-–—:") == title
            )
        except StopIteration:
            title_position = -1
        if title_position >= 0:
            for following in lines[title_position + 1:section_end]:
                if following in unique_titles:
                    break
                if action_start.match(following) or len(following.split()) > 8:
                    description_parts.append(following)

        clean_description, seen_desc = [], set()
        title_key = re.sub(r"\W+", " ", title.lower()).strip()
        for part in description_parts:
            part = re.sub(r"\s+", " ", part).strip()
            key = part.lower()
            if part and key not in seen_desc and re.sub(r"\W+", " ", key).strip() != title_key:
                seen_desc.add(key)
                clean_description.append(part)
        description = " ".join(clean_description)
        project_records.append(title + ("\n" + description if description else ""))

    return "\n\n".join(project_records)

def enrich_project_text_from_resume(resume_text, extracted_project_text):
    """Prefer reconstructed full project descriptions; preserve user extraction as fallback."""
    rebuilt = extract_projects_from_resume(resume_text)
    if rebuilt.strip():
        return rebuilt
    return str(extracted_project_text or "").strip()


def find_project_skills(project_text, required_skills):
    """Find job-required skills explicitly mentioned in a project's full description."""
    return [skill for skill in required_skills if _skill_present(skill, project_text)]


def classify_projects(project_text, required_skills):
    """Classify each project using its own full description, not neighboring resume text."""
    relevant, unmatched = [], []
    for project in split_project_entries(project_text):
        title, _, description = project.partition("\n")
        full_text = title + " " + description
        detected_skills = detect_skills_from_text(full_text)
        matched_skills = find_project_skills(full_text, required_skills)
        record = {
            "title": title.strip(),
            "text": full_text.strip(),
            "matched_skills": matched_skills,
            "detected_skills": list(dict.fromkeys(detected_skills)),
        }
        (relevant if matched_skills else unmatched).append(record)
    return relevant, unmatched

# ==================================================
# SIDEBAR
# ==================================================

st.sidebar.title("📄 Resume Analyzer")
st.sidebar.caption("Your personal career assistant")
st.sidebar.divider()

page = st.sidebar.radio(
    "NAVIGATION",
    [
        "Dashboard",
        "Resume Upload",
        "Career Recommendation",
        "Skill Gap Analysis",
        "Learning Roadmap",
        "Job Description Matching",
    ],
)

st.sidebar.divider()
st.sidebar.subheader("📄 Current Resume")

if st.session_state.resume_name:
    st.sidebar.success(st.session_state.resume_name)
    st.sidebar.caption(
        f"{len(st.session_state.resume_skills)} skills detected"
    )
else:
    st.sidebar.info("No resume analyzed yet.")


# ==================================================
# HEADER
# ==================================================

st.markdown(
    '<div class="main-title">Resume Analyzer</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="subtitle">'
    "Discover your skills. Understand your opportunities. "
    "Plan your career."
    "</div>",
    unsafe_allow_html=True,
)

st.divider()


# ==================================================
# CHECK RESUME
# ==================================================

def resume_is_ready():
    if not st.session_state.resume_name:
        st.warning(
            "Please upload and analyze your resume first."
        )
        return False

    if not st.session_state.resume_skills:
        st.warning(
            "No supported skills were detected in your resume."
        )
        return False

    return True


# ==================================================
# DASHBOARD
# ==================================================

if page == "Dashboard":

    st.subheader("Welcome to Your Career Dashboard")

    st.write(
        "Analyze your resume, discover suitable career roles, "
        "identify skill gaps, and compare your skills with "
        "job descriptions."
    )

    col1, col2, col3 = st.columns(3)

        
    with col1:
         # Get the career roles currently stored in MySQL
         job_roles = get_job_roles_from_database()
         # Display the actual number of career roles
         st.metric("Career Roles", len(job_roles))

    with col2:
        st.metric("Resume Formats", "PDF / DOCX")

    with col3:
        st.metric(
            "Skills Detected",
            len(st.session_state.resume_skills),
        )

    st.divider()

    if st.session_state.resume_name:
        st.success(
            f"Current resume: {st.session_state.resume_name}"
        )

        with st.expander("View detected skills"):
            st.write(
                ", ".join(
                    skill.title()
                    for skill in st.session_state.resume_skills
                )
            )
    else:
        st.info("Select Resume Upload to get started.")

    st.markdown("### Explore Features")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**📄 Resume Upload**")
        st.write("Upload your resume and extract skills.")

        st.markdown("**🎯 Career Recommendation**")
        st.write("Discover suitable career roles.")

        st.markdown("**📊 Skill Gap Analysis**")
        st.write("Identify skills not detected in your resume.")

    with col2:
        st.markdown("**📚 Learning Roadmap**")
        st.write("Explore learning suggestions.")

        st.markdown("**💼 Job Description Matching**")
        st.write("Compare your resume with a job posting.")


# ==================================================
# RESUME UPLOAD
# ==================================================

elif page == "Resume Upload":

    st.subheader("📄 Upload Your Resume")

    st.write("Choose a PDF or DOCX file.")

    uploaded_file = st.file_uploader(
        "Choose your resume",
        type=["pdf", "docx"],
        key="resume_uploader",
    )

    if uploaded_file is not None:

        st.success(f"Selected file: {uploaded_file.name}")

        if st.button("Extract My Skills", type="primary"):

            temp_path = None

            try:
                suffix = os.path.splitext(
                    uploaded_file.name
                )[1]

                with tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=suffix,
                ) as temp_file:
                    temp_file.write(uploaded_file.getvalue())
                    temp_path = temp_file.name

                with st.spinner("Analyzing your resume..."):
                    # Read the complete text from the uploaded PDF or DOCX.
                    resume_text = read_resume(temp_path)

                    # Extract the skills mentioned in the resume.
                    skills = extract_skills(resume_text)

                    # Extract the Projects section for review and matching.
                    project_text = extract_project_section(resume_text)
                    project_text = enrich_project_text_from_resume(
                        resume_text, project_text
                    )

                # Save a persistent copy of the uploaded resume.
                upload_folder = os.path.join(
                    os.getcwd(),
                    "uploaded_resumes",
                )
                os.makedirs(upload_folder, exist_ok=True)

                safe_name = os.path.basename(uploaded_file.name)
                permanent_path = os.path.join(
                    upload_folder,
                    safe_name,
                )

                with open(permanent_path, "wb") as output_file:
                    output_file.write(uploaded_file.getvalue())

                # Save the uploaded resume details in Streamlit session state.
                st.session_state.resume_name = safe_name
                st.session_state.resume_path = permanent_path

                # Store the complete text extracted from the resume.
                st.session_state.resume_text = resume_text
                
                # Store the skills extracted from the resume.
                st.session_state.resume_skills = skills

                # Store the project section extracted from the resume.
                st.session_state.resume_project_text = project_text
                # Reset the text-area widget so a newly uploaded resume does not
                # keep the previous resume's project text in Streamlit session state.
                st.session_state["edited_resume_projects"] = project_text

                # Clear previous job-matching display.
                st.session_state.job_match_result = None
                st.session_state.job_match_saved = False

                st.success("Resume analysis completed!")

            except Exception as error:
                st.error(f"Unable to process resume: {error}")

            finally:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)

    if st.session_state.resume_name:

        st.divider()
        st.subheader("Resume Analysis Results")

        st.write(
            f"**Current resume:** {st.session_state.resume_name}"
        )

        col1, col2 = st.columns(2)

        with col1:
            st.metric(
                "Skills Detected",
                len(st.session_state.resume_skills),
            )

        with col2:
            st.metric("Status", "Analyzed")

        if st.session_state.resume_skills:
            st.subheader("Skills Detected in Your Resume")

            columns = st.columns(3)

            for index, skill in enumerate(
                st.session_state.resume_skills
            ):
                with columns[index % 3]:
                    st.success(skill.title())
        else:
            st.warning("No supported skills were detected.")


        # Let users review, correct, or add project details extracted from the resume.
        st.divider()
        st.subheader("📁 Review or Edit Resume Projects")
        st.caption(
            "For best results, separate each project with a blank line. "
            "Include its title, technologies, and a short description."
        )

        edited_projects = st.text_area(
            "Projects extracted from your resume",
            value=st.session_state.resume_project_text,
            height=220,
            key="edited_resume_projects",
            placeholder=(
                "EventEase - Event booking system using FastAPI and MongoDB\n"
                "Built API endpoints and booking workflows.\n\n"
                "SahaFoods - Food ordering system using Flask and MySQL\n"
                "Implemented order management and payment integration."
            ),
        )

        if st.button("Save Projects", key="save_resume_projects"):
            st.session_state.resume_project_text = edited_projects
            st.success("Projects saved for this session!")


# ==================================================
# CAREER RECOMMENDATION
# ==================================================

elif page == "Career Recommendation":

    st.subheader("🎯 Career Recommendation")

    if resume_is_ready():

        st.write(
            f"Recommendations based on: "
            f"**{st.session_state.resume_name}**"
        )

        try:
            job_roles = get_job_roles_from_database()

            if not job_roles:
                st.warning("No career roles found in MySQL.")

            else:
                results = []

                for role, required_skills in job_roles.items():

                    _, percentage, matched, missing = (
                        calculate_job_match(
                            role,
                            st.session_state.resume_skills,
                            required_skills,
                        )
                    )

                    results.append({
                        "role": role,
                        "percentage": percentage,
                        "matched": matched,
                        "missing": missing,
                        "description": get_match_description(
                            percentage
                        ),
                    })

                results.sort(
                    key=lambda item: item["percentage"],
                    reverse=True,
                )

                st.session_state.career_results = results

                best = results[0]

                st.markdown("### Your Best Career Match")
                st.success(f"Recommended Career: {best['role']}")

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric(
                        "Match Percentage",
                        f"{best['percentage']:.2f}%",
                    )

                with col2:
                    st.metric(
                        "Matched Skills",
                        len(best["matched"]),
                    )

                with col3:
                    st.metric(
                        "Skills Not Detected",
                        len(best["missing"]),
                    )

                st.progress(int(best["percentage"]))
                st.write(best["description"])

                st.markdown("**Matched skills**")
                st.write(
                    ", ".join(
                        skill.title()
                        for skill in best["matched"]
                    ) or "No matched skills detected."
                )

                st.markdown("**Skills not detected**")
                st.write(
                    ", ".join(
                        skill.title()
                        for skill in best["missing"]
                    ) or "No missing tracked skills."
                )

                st.divider()
                st.markdown("### Compare All Career Roles")

                for result in results:

                    with st.expander(
                        f"{result['role']} — "
                        f"{result['percentage']:.2f}% match"
                    ):
                        st.write(result["description"])

                        left, right = st.columns(2)

                        with left:
                            st.markdown("**Matched skills**")
                            st.write(
                                ", ".join(
                                    s.title()
                                    for s in result["matched"]
                                ) or "None"
                            )

                        with right:
                            st.markdown("**Skills not detected**")
                            st.write(
                                ", ".join(
                                    s.title()
                                    for s in result["missing"]
                                ) or "None"
                            )

        except Exception as error:
            st.error(f"Career recommendation failed: {error}")


# ==================================================
# SKILL GAP ANALYSIS
# ==================================================

elif page == "Skill Gap Analysis":

    st.subheader("📊 Skill Gap Analysis")

    if resume_is_ready():

        st.write(
            f"Analyzing: **{st.session_state.resume_name}**"
        )

        try:
            job_roles = get_job_roles_from_database()

            if not job_roles:
                st.warning("No career roles found in MySQL.")
            else:
                selected_role = st.selectbox(
                    "Select a career role",
                    list(job_roles.keys()),
                )

                required_skills = job_roles[selected_role]

                _, percentage, matched, missing = (
                    calculate_job_match(
                        selected_role,
                        st.session_state.resume_skills,
                        required_skills,
                    )
                )

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("Overall Match", f"{percentage:.2f}%")

                with col2:
                    st.metric("Matched Skills", len(matched))

                with col3:
                    st.metric("Skills to Improve", len(missing))

                st.progress(int(percentage))

                left, right = st.columns(2)

                with left:
                    st.markdown("### ✅ Matched Skills")

                    for skill in matched:
                        st.success(skill.title())

                    if not matched:
                        st.info("No matched skills detected.")

                with right:
                    st.markdown("### 📌 Skills Not Detected")

                    for skill in missing:
                        st.warning(skill.title())

                    if not missing:
                        st.success("No missing tracked skills.")

                st.markdown("### Improvement Suggestions")

                suggestions = get_improvement_suggestions(missing)

                if suggestions:
                    for suggestion in suggestions:
                        st.write(f"- {suggestion}")
                else:
                    st.success("No tracked skill gaps were detected.")

        except Exception as error:
            st.error(f"Skill gap analysis failed: {error}")


# ==================================================
# LEARNING ROADMAP
# ==================================================

elif page == "Learning Roadmap":

    st.subheader("📚 Learning Roadmap")

    if resume_is_ready():

        st.write(
            f"Learning suggestions based on: "
            f"**{st.session_state.resume_name}**"
        )

        try:
            job_roles = get_job_roles_from_database()

            if not job_roles:
                st.warning("No career roles found in MySQL.")
            else:
                selected_role = st.selectbox(
                    "Choose your target career",
                    list(job_roles.keys()),
                )

                _, percentage, matched, missing = (
                    calculate_job_match(
                        selected_role,
                        st.session_state.resume_skills,
                        job_roles[selected_role],
                    )
                )

                st.metric("Current Match", f"{percentage:.2f}%")

                if missing:
                    st.markdown("### Your Suggested Learning Plan")

                    for index, skill in enumerate(missing, start=1):
                        with st.expander(
                            f"Step {index}: Learn {skill.title()}"
                        ):
                            st.write(
                                f"Study {skill.title()} fundamentals, "
                                "practise with exercises, and build "
                                "a small project."
                            )

                            st.write(
                                "Add this skill to your resume only "
                                "if you genuinely have it."
                            )
                else:
                    st.success("No tracked skill gaps were detected.")

        except Exception as error:
            st.error(f"Learning roadmap failed: {error}")


# ==================================================
# JOB DESCRIPTION MATCHING
# ==================================================

elif page == "Job Description Matching":

    st.subheader("💼 Job Description Matching")

    if resume_is_ready():

        st.write(
            f"Comparing your resume: "
            f"**{st.session_state.resume_name}**"
        )

        # Keep the user's name outside the button block.
        user_name = st.text_input(
            "Your name",
            value="Manasa",
            key="analysis_user_name",
        )

        # NEW: Enter the job role
        job_role = st.text_input(
            "Enter the job role",
            placeholder="Example: Data Scientist",
            key="job_role_input",
)

        job_description = st.text_area(
            "Paste the job description",
            height=250,
            placeholder=(
                "Paste the job title, responsibilities, "
                "qualifications, and required skills..."
            ),
            key="job_description_input",
        )

        if st.button("Analyze Job Match", type="primary"):

            if not user_name.strip():
                st.warning("Please enter your name.")

            elif not job_description.strip():
                st.warning("Please paste a job description.")

            else:
                try:
                    # Use the latest text in the project editor, even if the user
                    # has not clicked "Save Projects" again.
                    project_text_for_analysis = str(
                        st.session_state.get(
                            "edited_resume_projects",
                            st.session_state.resume_project_text,
                        ) or ""
                    ).strip()
                    if not project_text_for_analysis:
                        project_text_for_analysis = enrich_project_text_from_resume(
                            st.session_state.get("resume_text", ""),
                            st.session_state.resume_project_text,
                        )
                    st.session_state.resume_project_text = project_text_for_analysis

                    # Detect skills in the project descriptions as well as in the
                    # resume's skills section. This means Python/MySQL mentioned
                    # inside SahaFoods can count as evidence for the job match.
                    # Combine skills from the original resume, the complete project
                    # descriptions, and a direct alias-aware scan of both text sources.
                    project_skills = extract_skills(project_text_for_analysis)
                    text_skills = detect_skills_from_text(
                        st.session_state.get("resume_text", "") + "\n"
                        + project_text_for_analysis
                    )
                    combined_skills = list(dict.fromkeys(
                        [str(skill).strip() for skill in st.session_state.resume_skills]
                        + [str(skill).strip() for skill in project_skills]
                        + text_skills
                    ))

                    # Normalize skills from the job description and compare them
                    # against the entire extracted resume plus all project descriptions.
                    required_skills = extract_job_required_skills(job_description)
                    evidence_text = (
                        st.session_state.get("resume_text", "") + "\n" +
                        project_text_for_analysis + "\n" +
                        " ".join(str(skill) for skill in combined_skills)
                    )
                    matched_skills = [skill for skill in required_skills
                                      if _skill_present(skill, evidence_text)]
                    missing_skills = [skill for skill in required_skills
                                      if skill not in matched_skills]
                    match_percentage = (
                        100.0 * len(matched_skills) / len(required_skills)
                        if required_skills else 0.0
                    )
                    result = match_resume_with_description(
                        combined_skills,
                        job_description,
                    )
                    # Override inconsistent matching-library aliases with the
                    # normalized, explainable results calculated above.
                    result["required_skills"] = required_skills
                    result["matched_skills"] = matched_skills
                    result["missing_skills"] = missing_skills
                    result["match_percentage"] = match_percentage
                    result["description"] = get_match_description(match_percentage)
                    result["suggestions"] = get_improvement_suggestions(missing_skills)
                    result["project_skills"] = project_skills
                    result["skills_used_for_match"] = combined_skills

                    # Compare each clean project entry with the detected job skills.
                    relevant_projects, unmatched_projects = classify_projects(
                        project_text_for_analysis,
                        required_skills,
                    )
                    result["relevant_projects"] = relevant_projects
                    result["unmatched_projects"] = unmatched_projects

                    st.session_state.job_match_result = result
                    st.session_state.job_match_saved = False

                    if result["required_skills"]:
                        with st.spinner("Saving result to MySQL..."):

                            save_job_match_to_mysql(
                                user_name=user_name,
                                resume_name=st.session_state.resume_name,
                                resume_path=st.session_state.resume_path,
                                job_description=job_description,
                                match_percentage=result[
                                    "match_percentage"
                                ],
                            )

                        st.session_state.job_match_saved = True

                except Exception as error:
                    st.error(
                        f"Unable to analyze or save the job match: {error}"
                    )

        result = st.session_state.job_match_result

        if result is not None:

            st.divider()
            st.markdown("### Job Match Results")

            if not result["required_skills"]:
                st.warning(result["description"])

            else:
                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric(
                        "Match Percentage",
                        f"{result['match_percentage']:.2f}%",
                    )

                with col2:
                    st.metric(
                        "Matched Skills",
                        len(result["matched_skills"]),
                    )

                with col3:
                    st.metric(
                        "Skills Not Detected",
                        len(result["missing_skills"]),
                    )

                st.progress(int(result["match_percentage"]))
                st.write(result["description"])

                left, right = st.columns(2)

                with left:
                    st.markdown("### ✅ Matched Skills")

                    if result["matched_skills"]:
                        for skill in result["matched_skills"]:
                            st.success(skill.title())
                    else:
                        st.info("No matched skills detected.")

                with right:
                    st.markdown("### 📌 Skills Not Detected")

                    if result["missing_skills"]:
                        for skill in result["missing_skills"]:
                            st.warning(skill.title())
                    else:
                        st.success("No missing tracked skills.")

                st.markdown("### Suggestions")

                for suggestion in result["suggestions"]:
                    st.write(f"- {suggestion}")

                # Display project-level matches and the skills found in each project.
                st.divider()
                st.markdown("### 🧩 Projects Compared with the Job")
                st.caption(
                    "Each project title is grouped with its full multiline description. "
                    "Skills are extracted from the complete project text, then compared "
                    "with skills detected in the job description. Review the results because "
                    "this is keyword-based matching."
                )

                project_left, project_right = st.columns(2)

                with project_left:
                    st.markdown("#### ✅ Projects with Matching Skills")
                    if result.get("relevant_projects"):
                        for project in result["relevant_projects"]:
                            st.success(project.get("title", project["text"].split("\n", 1)[0]))
                            with st.expander("View full project description"):
                                st.write(project["text"])
                            st.caption(
                                "Skills detected in this project: "
                                + (", ".join(skill.title() for skill in project.get("detected_skills", [])) or "No skills recognized by the skill extractor")
                            )
                            st.caption(
                                "Skills matching this job: "
                                + (", ".join(skill.title() for skill in project["matched_skills"]) or "None")
                            )
                    else:
                        st.info("No projects with matching required skills were detected.")

                with project_right:
                    st.markdown("#### 📌 Unmatched Projects")
                    if result.get("unmatched_projects"):
                        for project in result["unmatched_projects"]:
                            st.warning(project.get("title", project["text"].split("\n", 1)[0]))
                            with st.expander("View full project description"):
                                st.write(project["text"])
                            st.caption(
                                "Skills detected in this project: "
                                + (", ".join(skill.title() for skill in project.get("detected_skills", [])) or "No skills recognized by the skill extractor")
                            )
                            st.caption("No detected project skills matched the job's required skills.")
                    else:
                        st.info("No unmatched project entries.")

                if st.session_state.job_match_saved:
                    st.success(
                        "Job description and match result saved to MySQL."
                    )


# ==================================================
# FOOTER
# ==================================================

st.divider()

st.caption(
    "Resume Analyzer | Resume & Job Description Analysis System"
)
