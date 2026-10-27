
import mysql.connector
from mysql.connector import Error


# ---------------------------------
# 1. MySQL Database Configuration
# ---------------------------------

db = {
    "host": "localhost",
    "user": "root",
    "password": "root",
    "database": "career_system"
}


# ---------------------------------
# 2. Create Database Connection
# ---------------------------------

def create_connection():
    try:
        connection = mysql.connector.connect(**db)
        return connection

    except Error as error:
        print("Database connection failed:", error)
        return None


# ---------------------------------
# 3. Get All Career Roles
# ---------------------------------

def get_all_jobs():
    connection = create_connection()

    if connection is None:
        return []

    cursor = None

    try:
        cursor = connection.cursor()
        cursor.execute("SELECT id, job_name FROM jobs ORDER BY id")
        return cursor.fetchall()

    except Error as error:
        print("Error retrieving jobs:", error)
        return []

    finally:
        if cursor is not None:
            cursor.close()
        if connection.is_connected():
            connection.close()


# ---------------------------------
# 4. Get Skills Required for a Job
# ---------------------------------

def get_job_skills(job_id):
    connection = create_connection()

    if connection is None:
        return []

    cursor = None

    try:
        cursor = connection.cursor()

        query = """
        SELECT s.id, s.skill_name
        FROM skills s
        JOIN job_skills js ON s.id = js.skill_id
        WHERE js.job_id = %s
        ORDER BY s.skill_name
        """

        cursor.execute(query, (job_id,))
        return cursor.fetchall()

    except Error as error:
        print("Error retrieving job skills:", error)
        return []

    finally:
        if cursor is not None:
            cursor.close()
        if connection.is_connected():
            connection.close()


# ---------------------------------
# 5. Get All Available Skills
# ---------------------------------

def get_all_skills():
    connection = create_connection()

    if connection is None:
        return []

    cursor = None

    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id, skill_name FROM skills ORDER BY skill_name"
        )
        return cursor.fetchall()

    except Error as error:
        print("Error retrieving skills:", error)
        return []

    finally:
        if cursor is not None:
            cursor.close()
        if connection.is_connected():
            connection.close()


# ---------------------------------
# 6. Save User
# ---------------------------------

def save_user(name):
    connection = create_connection()

    if connection is None:
        return None

    cursor = None

    try:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO users (name) VALUES (%s)",
            (name,)
        )

        connection.commit()
        return cursor.lastrowid

    except Error as error:
        connection.rollback()
        print("Error saving user:", error)
        return None

    finally:
        if cursor is not None:
            cursor.close()
        if connection.is_connected():
            connection.close()


# ---------------------------------
# 7. Save Uploaded Resume Details
# ---------------------------------

def save_resume(user_id, resume_name, resume_path):
    connection = create_connection()

    if connection is None:
        return None

    cursor = None

    try:
        cursor = connection.cursor()

        query = """
        INSERT INTO resumes (user_id, resume_name, resume_path)
        VALUES (%s, %s, %s)
        """

        cursor.execute(
            query,
            (user_id, resume_name, resume_path)
        )

        connection.commit()
        return cursor.lastrowid

    except Error as error:
        connection.rollback()
        print("Error saving resume:", error)
        return None

    finally:
        if cursor is not None:
            cursor.close()
        if connection.is_connected():
            connection.close()


# ---------------------------------
# 8. Save Skills Found in a Resume
# ---------------------------------

def save_resume_skills(resume_id, skill_ids):
    connection = create_connection()

    if connection is None:
        return False

    cursor = None

    try:
        cursor = connection.cursor()

        cursor.execute(
            "DELETE FROM resume_skills WHERE resume_id = %s",
            (resume_id,)
        )

        query = """
        INSERT INTO resume_skills (resume_id, skill_id)
        VALUES (%s, %s)
        """

        for skill_id in skill_ids:
            cursor.execute(query, (resume_id, skill_id))

        connection.commit()
        return True

    except Error as error:
        connection.rollback()
        print("Error saving resume skills:", error)
        return False

    finally:
        if cursor is not None:
            cursor.close()
        if connection.is_connected():
            connection.close()


# ---------------------------------
# 9. Save Career Match Result
# ---------------------------------

def save_career_result(user_id, resume_id, job_id, match_percentage):
    connection = create_connection()

    if connection is None:
        return False

    cursor = None

    try:
        cursor = connection.cursor()

        query = """
        INSERT INTO career_results
        (user_id, resume_id, job_id, match_percentage)
        VALUES (%s, %s, %s, %s)
        """

        cursor.execute(
            query,
            (user_id, resume_id, job_id, match_percentage)
        )

        connection.commit()
        return True

    except Error as error:
        connection.rollback()
        print("Error saving career result:", error)
        return False

    finally:
        if cursor is not None:
            cursor.close()
        if connection.is_connected():
            connection.close()


# ---------------------------------
# 10. Get Previous Career Results
# ---------------------------------

def get_career_results(user_id):
    connection = create_connection()

    if connection is None:
        return []

    cursor = None

    try:
        cursor = connection.cursor()

        query = """
        SELECT j.job_name,
               cr.match_percentage,
               cr.recommended_at
        FROM career_results cr
        JOIN jobs j ON cr.job_id = j.id
        WHERE cr.user_id = %s
        ORDER BY cr.recommended_at DESC
        """

        cursor.execute(query, (user_id,))
        return cursor.fetchall()

    except Error as error:
        print("Error retrieving career results:", error)
        return []

    finally:
        if cursor is not None:
            cursor.close()
        if connection.is_connected():
            connection.close()


# ---------------------------------
# 11. Save Job Description
# ---------------------------------

def save_job_description(job_title, description):
    connection = create_connection()

    if connection is None:
        return None

    cursor = None

    try:
        cursor = connection.cursor()

        query = """
        INSERT INTO job_descriptions (job_title, description)
        VALUES (%s, %s)
        """

        cursor.execute(query, (job_title, description))
        connection.commit()

        return cursor.lastrowid

    except Error as error:
        connection.rollback()
        print("Error saving job description:", error)
        return None

    finally:
        if cursor is not None:
            cursor.close()
        if connection.is_connected():
            connection.close()


# ---------------------------------
# 12. Save Job Description Match Result
# ---------------------------------

def save_job_description_result(
    user_id,
    resume_id,
    job_description_id,
    match_percentage
):
    connection = create_connection()

    if connection is None:
        return False

    cursor = None

    try:
        cursor = connection.cursor()

        query = """
        INSERT INTO job_description_results
        (user_id, resume_id, job_description_id, match_percentage)
        VALUES (%s, %s, %s, %s)
        """

        cursor.execute(
            query,
            (
                user_id,
                resume_id,
                job_description_id,
                match_percentage
            )
        )

        connection.commit()
        return True

    except Error as error:
        connection.rollback()
        print("Error saving job description match:", error)
        return False

    finally:
        if cursor is not None:
            cursor.close()
        if connection.is_connected():
            connection.close()


# ---------------------------------
# 13. Test Database Functions
# ---------------------------------

if __name__ == "__main__":

    connection = create_connection()

    if connection is not None:
        print("MySQL connection successful!")
        connection.close()

    print("\nCareer Roles:")
    for job in get_all_jobs():
        print(job)

    print("\nAvailable Skills:")
    for skill in get_all_skills():
        print(skill)

    print("\nSkills required for Backend Developer:")
    for skill in get_job_skills(1):
        print(skill)
