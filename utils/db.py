import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import mysql.connector
from mysql.connector import pooling
import pandas as pd
import streamlit as st
from config import DB_CONFIG

# Override with Streamlit secrets if available (Streamlit Cloud deployment)
def _build_db_config():
    try:
        secrets = st.secrets
        return {
            "host":     secrets.get("DB_HOST", DB_CONFIG["host"]),
            "user":     secrets.get("DB_USER", DB_CONFIG["user"]),
            "password": secrets.get("DB_PASSWORD", DB_CONFIG["password"]),
            "database": secrets.get("DB_NAME", DB_CONFIG["database"]),
            "port":     int(secrets.get("DB_PORT", DB_CONFIG["port"])),
            "ssl_disabled": False,
        }
    except Exception:
        return DB_CONFIG


@st.cache_resource
def get_connection_pool():
    cfg = _build_db_config()
    return pooling.MySQLConnectionPool(
        pool_name="mobility_pool",
        pool_size=5,
        **cfg
    )

def get_conn():
    pool = get_connection_pool()
    return pool.get_connection()

def run_query(sql: str, params=None) -> pd.DataFrame:
    conn = get_conn()
    try:
        df = pd.read_sql(sql, conn, params=params)
        return df
    finally:
        conn.close()

def run_write(sql: str, params=None, many=False):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        if many:
            cursor.executemany(sql, params)
        else:
            cursor.execute(sql, params)
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()

# ── Auth ──────────────────────────────────────────────────────────────────────

def get_employee_by_email(email: str) -> pd.DataFrame:
    return run_query(
        "SELECT * FROM employees WHERE email = %s AND is_active = TRUE",
        (email,)
    )

def get_employee_by_id(emp_id: int) -> pd.DataFrame:
    return run_query(
        "SELECT * FROM employees WHERE employee_id = %s",
        (emp_id,)
    )

def create_employee(data: dict) -> int:
    sql = """
        INSERT INTO employees
            (email, full_name, current_department, current_role,
             hire_date, location, employee_level, manager_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    return run_write(sql, (
        data["email"], data["full_name"], data["current_department"],
        data["current_role"], data["hire_date"], data["location"],
        data["employee_level"], data.get("manager_id")
    ))

# ── Job Postings ──────────────────────────────────────────────────────────────

def get_open_jobs() -> pd.DataFrame:
    return run_query("""
        SELECT jp.*, e.full_name AS hiring_manager_name
        FROM job_postings jp
        LEFT JOIN employees e ON jp.hiring_manager_id = e.employee_id
        WHERE jp.status = 'Open'
        ORDER BY jp.posting_date DESC
    """)

def get_all_jobs() -> pd.DataFrame:
    return run_query("""
        SELECT jp.*, e.full_name AS hiring_manager_name
        FROM job_postings jp
        LEFT JOIN employees e ON jp.hiring_manager_id = e.employee_id
        ORDER BY jp.posting_date DESC
    """)

def get_job_by_id(job_id: int) -> pd.DataFrame:
    return run_query(
        "SELECT * FROM job_postings WHERE job_id = %s", (job_id,)
    )

def create_job_posting(data: dict) -> int:
    sql = """
        INSERT INTO job_postings
            (job_title, department, location, job_level, min_experience,
             max_experience, job_description, key_responsibilities,
             posting_date, closing_date, status, hiring_manager_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """
    return run_write(sql, (
        data["job_title"], data["department"], data["location"],
        data["job_level"], data["min_experience"], data["max_experience"],
        data["job_description"], data["key_responsibilities"],
        data["posting_date"], data["closing_date"],
        data.get("status", "Open"), data.get("hiring_manager_id")
    ))

def update_job_status(job_id: int, status: str):
    run_write(
        "UPDATE job_postings SET status = %s WHERE job_id = %s",
        (status, job_id)
    )

# ── Skills ────────────────────────────────────────────────────────────────────

def get_all_skills() -> pd.DataFrame:
    return run_query("SELECT * FROM skills_master ORDER BY skill_name")

def get_employee_skills(emp_id: int) -> pd.DataFrame:
    return run_query("""
        SELECT es.*, sm.skill_name, sm.skill_category, sm.is_technical
        FROM employee_skills es
        JOIN skills_master sm ON es.skill_id = sm.skill_id
        WHERE es.employee_id = %s
    """, (emp_id,))

def upsert_employee_skill(emp_id, skill_id, proficiency, years_exp, last_used, cert_status):
    sql = """
        INSERT INTO employee_skills
            (employee_id, skill_id, proficiency_level, years_experience, last_used, certification_status)
        VALUES (%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            proficiency_level = VALUES(proficiency_level),
            years_experience  = VALUES(years_experience),
            last_used         = VALUES(last_used),
            certification_status = VALUES(certification_status)
    """
    run_write(sql, (emp_id, skill_id, proficiency, years_exp, last_used, cert_status))

# ── Performance ───────────────────────────────────────────────────────────────

def get_employee_performance(emp_id: int) -> pd.DataFrame:
    return run_query(
        "SELECT * FROM performance_history WHERE employee_id = %s ORDER BY review_date DESC",
        (emp_id,)
    )

def get_all_performance() -> pd.DataFrame:
    return run_query("""
        SELECT ph.*, e.full_name, e.current_department
        FROM performance_history ph
        JOIN employees e ON ph.employee_id = e.employee_id
        ORDER BY ph.review_date DESC
    """)

# ── Training ──────────────────────────────────────────────────────────────────

def get_employee_training(emp_id: int) -> pd.DataFrame:
    return run_query(
        "SELECT * FROM training_completed WHERE employee_id = %s ORDER BY completion_date DESC",
        (emp_id,)
    )

# ── Match Results ─────────────────────────────────────────────────────────────

def get_matches_for_employee(emp_id: int) -> pd.DataFrame:
    return run_query("""
        SELECT mr.*, jp.job_title, jp.department, jp.location, jp.job_level
        FROM match_results mr
        JOIN job_postings jp ON mr.job_id = jp.job_id
        WHERE mr.employee_id = %s
        ORDER BY mr.match_score DESC
    """, (emp_id,))

def get_matches_for_job(job_id: int) -> pd.DataFrame:
    return run_query("""
        SELECT mr.*, e.full_name, e.current_department, e.current_role, e.employee_level
        FROM match_results mr
        JOIN employees e ON mr.employee_id = e.employee_id
        WHERE mr.job_id = %s
        ORDER BY mr.match_score DESC
    """, (job_id,))

def upsert_match(job_id, emp_id, scores: dict):
    sql = """
        INSERT INTO match_results
            (job_id, employee_id, match_score, skill_match_score,
             experience_match_score, performance_match_score, growth_potential_score)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            match_score = VALUES(match_score),
            skill_match_score = VALUES(skill_match_score),
            experience_match_score = VALUES(experience_match_score),
            performance_match_score = VALUES(performance_match_score),
            growth_potential_score = VALUES(growth_potential_score),
            match_date = CURRENT_TIMESTAMP
    """
    run_write(sql, (
        job_id, emp_id,
        scores["match_score"], scores["skill_match_score"],
        scores["experience_match_score"], scores["performance_match_score"],
        scores["growth_potential_score"]
    ))

def mark_applied(job_id: int, emp_id: int):
    # Ensure a row exists first, then mark applied
    run_write(
        """INSERT INTO match_results (job_id, employee_id, match_score, skill_match_score,
               experience_match_score, performance_match_score, growth_potential_score, employee_applied)
           VALUES (%s, %s, 0, 0, 0, 0, 0, TRUE)
           ON DUPLICATE KEY UPDATE employee_applied = TRUE""",
        (job_id, emp_id)
    )

def mark_viewed(job_id: int, emp_id: int):
    # Ensure a row exists first, then mark viewed
    run_write(
        """INSERT INTO match_results (job_id, employee_id, match_score, skill_match_score,
               experience_match_score, performance_match_score, growth_potential_score, employee_viewed)
           VALUES (%s, %s, 0, 0, 0, 0, 0, TRUE)
           ON DUPLICATE KEY UPDATE employee_viewed = TRUE""",
        (job_id, emp_id)
    )

# ── Career Interests ──────────────────────────────────────────────────────────

def get_career_interests(emp_id: int) -> pd.DataFrame:
    return run_query(
        "SELECT * FROM career_interests WHERE employee_id = %s", (emp_id,)
    )

def upsert_career_interest(emp_id, dept, role, timeline, relocate, notes):
    sql = """
        INSERT INTO career_interests
            (employee_id, interested_department, interested_role,
             target_timeline, willing_to_relocate, notes)
        VALUES (%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            interested_department = VALUES(interested_department),
            interested_role       = VALUES(interested_role),
            target_timeline       = VALUES(target_timeline),
            willing_to_relocate   = VALUES(willing_to_relocate),
            notes                 = VALUES(notes)
    """
    run_write(sql, (emp_id, dept, role, timeline, relocate, notes))

# ── HR Analytics helpers ──────────────────────────────────────────────────────

def get_all_employees() -> pd.DataFrame:
    return run_query("""
        SELECT e.*, m.full_name AS manager_name
        FROM employees e
        LEFT JOIN employees m ON e.manager_id = m.employee_id
        WHERE e.is_active = TRUE
        ORDER BY e.full_name
    """)

def get_dept_skill_summary() -> pd.DataFrame:
    return run_query("""
        SELECT e.current_department, sm.skill_category,
               COUNT(*) AS skill_count,
               AVG(es.proficiency_level) AS avg_proficiency
        FROM employee_skills es
        JOIN employees e ON es.employee_id = e.employee_id
        JOIN skills_master sm ON es.skill_id = sm.skill_id
        WHERE e.is_active = TRUE
        GROUP BY e.current_department, sm.skill_category
    """)

def get_job_required_skills(job_id: int) -> pd.DataFrame:
    return run_query("""
        SELECT jrs.*, sm.skill_name, sm.skill_category
        FROM job_required_skills jrs
        JOIN skills_master sm ON jrs.skill_id = sm.skill_id
        WHERE jrs.job_id = %s
    """, (job_id,))
