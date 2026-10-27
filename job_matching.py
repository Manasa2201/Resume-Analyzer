
import os
import re

from database import (
    get_all_jobs,
    get_job_skills,
    get_all_skills,
    save_user,
    save_resume,
    save_resume_skills,
    save_career_result
)

# Skills supported by our system
SUPPORTED_SKILLS = [
    "python",
    "sql",
    "fastapi",
    "flask",
    "javascript",
    "html",
    "css",
    "react",
    "angular",
    "mongodb",
    "mysql",
    "git",
    "github",
    "pandas",
    "numpy",
    "machine learning",
    "docker",
    "linux"
]


# Get job roles and their required skills from MySQL
def get_job_roles_from_database():
    jobs = get_all_jobs()
    job_roles = {}

    for job_id, job_name in jobs:
        skills_data = get_job_skills(job_id)

        job_roles[job_name] = [
            skill_name
            for skill_id, skill_name in skills_data
        ]

    return job_roles


# Extract supported skills from job-description text
def extract_skills_from_description(description):
    description_lower = description.lower()
    found_skills = []

    for skill in SUPPORTED_SKILLS:
        pattern = r"\b" + re.escape(skill) + r"\b"

        if re.search(pattern, description_lower):
            found_skills.append(skill)

    return found_skills


# Calculate resume-to-job skill match
def calculate_job_match(role, resume_skills, required_skills):
    resume_set = {
        skill.strip().lower()
        for skill in resume_skills
    }

    required_set = {
        skill.strip().lower()
        for skill in required_skills
    }

    if not required_set:
        return role, 0, [], []

    matched = sorted(resume_set & required_set)
    missing = sorted(required_set - resume_set)

    percentage = round(
        len(matched) / len(required_set) * 100,
        2
    )

    return role, percentage, matched, missing


# Explain the match percentage
def get_match_description(percentage):
    if percentage == 100:
        return "All tracked required skills were detected in the resume."
    elif percentage >= 75:
        return "Strong skill match. Review any remaining requirements."
    elif percentage >= 50:
        return "Moderate skill match. Review the missing skills."
    elif percentage > 0:
        return "Low skill match. Several required skills were not detected."
    else:
        return "No tracked required skills were detected."


# Suggest improvements for skills not detected
def get_improvement_suggestions(missing_skills):
    suggestions = []

    for skill in missing_skills:
        suggestions.append(
            f"Study {skill}, practise it, and build a small project. "
            f"Add it to your resume only if you genuinely have that skill."
        )

    return suggestions


# Compare resume skills with a user-provided job description
def match_resume_with_description(resume_skills, job_description):
    required_skills = extract_skills_from_description(
        job_description
    )

    role = "User-Provided Job Description"

    if not required_skills:
        return {
            "role": role,
            "match_percentage": 0,
            "required_skills": [],
            "matched_skills": [],
            "missing_skills": [],
            "description": (
                "No supported skills were detected. "
                "Please check the job description."
            ),
            "suggestions": []
        }

    _, percentage, matched, missing = calculate_job_match(
        role,
        resume_skills,
        required_skills
    )

    return {
        "role": role,
        "match_percentage": percentage,
        "required_skills": required_skills,
        "matched_skills": matched,
        "missing_skills": missing,
        "description": get_match_description(percentage),
        "suggestions": get_improvement_suggestions(missing)
    }


# Save career analysis to MySQL
def save_analysis_to_database(
    user_name,
    resume_path,
    resume_skills,
    career_results
):
    user_id = save_user(user_name)

    if user_id is None:
        return False

    resume_name = os.path.basename(resume_path)

    resume_id = save_resume(
        user_id,
        resume_name,
        resume_path
    )

    if resume_id is None:
        return False

    all_skills = get_all_skills()

    skill_id_map = {
        name.lower(): skill_id
        for skill_id, name in all_skills
    }

    skill_ids = [
        skill_id_map[skill.lower()]
        for skill in resume_skills
        if skill.lower() in skill_id_map
    ]

    if not save_resume_skills(resume_id, skill_ids):
        return False

    job_id_map = {
        name: job_id
        for job_id, name in get_all_jobs()
    }

    for role, result in career_results.items():
        job_id = job_id_map.get(role)

        if job_id is None:
            continue

        if not save_career_result(
            user_id,
            resume_id,
            job_id,
            result["match"]
        ):
            return False

    return True


# Test job-description matching
if __name__ == "__main__":
    resume_skills = [
        "python",
        "fastapi",
        "flask",
        "git",
        "mongodb"
    ]

    job_description = """
    Backend Developer required.
    Skills: Python, SQL, FastAPI, Git, Docker.
    """

    result = match_resume_with_description(
        resume_skills,
        job_description
    )

    print("\nJOB DESCRIPTION MATCH ANALYSIS")
    print("Required skills:", result["required_skills"])
    print("Match:", result["match_percentage"], "%")
    print("Description:", result["description"])
    print("Matched skills:", result["matched_skills"])
    print("Missing skills:", result["missing_skills"])

    print("\nSUGGESTIONS:")
    for suggestion in result["suggestions"]:
        print("-", suggestion)