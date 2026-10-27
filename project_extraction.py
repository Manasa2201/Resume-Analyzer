
import re


def extract_project_section(resume_text):
    """
    Extract the Projects section from resume text.
    Returns the section as text for the user to review.
    """

    lines = resume_text.splitlines()

    start_pattern = re.compile(
        r"^\s*(projects|personal projects|academic projects|key projects)\s*:?\s*$",
        re.IGNORECASE,
    )

    end_pattern = re.compile(
        r"^\s*(experience|work experience|education|skills|"
        r"certifications|achievements|internship|internships|"
        r"languages|interests|summary|professional summary|"
        r"technical skills|contact|contact information)\s*:?\s*$",
        re.IGNORECASE,
    )

    project_lines = []
    inside_projects = False

    for line in lines:
        cleaned_line = line.strip()

        if not inside_projects:
            if start_pattern.match(cleaned_line):
                inside_projects = True
            continue

        if end_pattern.match(cleaned_line):
            break

        if cleaned_line:
            project_lines.append(cleaned_line)

    return "\n".join(project_lines)
