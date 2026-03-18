import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
from datetime import date
from utils.db import get_employee_by_email, create_employee, run_write, get_all_skills, upsert_employee_skill
from utils.auth import hash_password

st.set_page_config(page_title="Register", page_icon="📝")
st.title("📝 Register")

DEPARTMENTS = ["Engineering", "Product", "Design", "Marketing", "Sales", "HR", "Finance", "Operations"]
LEVELS = ["Junior", "Mid", "Senior", "Lead", "Principal", "Director"]
LOCATIONS = ["Remote", "New York", "San Francisco", "London", "Austin", "Chicago"]
PROFICIENCY_LABELS = {1: "1 - Beginner", 2: "2 - Basic", 3: "3 - Intermediate", 4: "4 - Advanced", 5: "5 - Expert"}

# ── Step state ────────────────────────────────────────────────────────────────
if "reg_step" not in st.session_state:
    st.session_state["reg_step"] = 1
if "reg_emp_id" not in st.session_state:
    st.session_state["reg_emp_id"] = None

step = st.session_state["reg_step"]

# ── Step indicator ────────────────────────────────────────────────────────────
col_s1, col_s2 = st.columns(2)
col_s1.markdown(f"{'**' if step == 1 else ''}Step 1: Account Info{'**' if step == 1 else ''} {'✅' if step > 1 else ''}")
col_s2.markdown(f"{'**' if step == 2 else ''}Step 2: Add Your Skills{'**' if step == 2 else ''}")
st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Basic info
# ══════════════════════════════════════════════════════════════════════════════
if step == 1:
    with st.form("register_form"):
        col1, col2 = st.columns(2)
        with col1:
            full_name = st.text_input("Full Name *")
            email = st.text_input("Email *")
            password = st.text_input("Password *", type="password")
            confirm = st.text_input("Confirm Password *", type="password")
        with col2:
            department = st.selectbox("Department", DEPARTMENTS)
            current_role = st.text_input("Current Role / Title *")
            level = st.selectbox("Employee Level", LEVELS)
            location = st.selectbox("Location", LOCATIONS)
            hire_date = st.date_input("Hire Date", value=date.today())

        submitted = st.form_submit_button("Next: Add Skills →", type="primary")

    if submitted:
        if not all([full_name.strip(), email.strip(), password, current_role.strip()]):
            st.error("Please fill in all required fields.")
        elif password != confirm:
            st.error("Passwords do not match.")
        elif len(password) < 6:
            st.error("Password must be at least 6 characters.")
        else:
            existing = get_employee_by_email(email.strip().lower())
            if not existing.empty:
                st.error("An account with this email already exists.")
            else:
                try:
                    emp_id = create_employee({
                        "email": email.strip().lower(),
                        "full_name": full_name.strip(),
                        "current_department": department,
                        "current_role": current_role.strip(),
                        "hire_date": hire_date.strftime("%Y-%m-%d"),
                        "location": location,
                        "employee_level": level,
                        "manager_id": None,
                    })
                    pw_hash = hash_password(password)
                    run_write(
                        "UPDATE employees SET password_hash = %s WHERE employee_id = %s",
                        (pw_hash, emp_id)
                    )
                    st.session_state["reg_emp_id"] = emp_id
                    st.session_state["reg_step"] = 2
                    st.rerun()
                except Exception as e:
                    st.error(f"Registration failed: {e}")

    st.markdown("Already have an account? [Login](login)")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Skill selection
# ══════════════════════════════════════════════════════════════════════════════
elif step == 2:
    emp_id = st.session_state["reg_emp_id"]
    st.subheader("Add Your Skills")
    st.caption("Select skills from the list and set your proficiency level. You can always update these later.")

    all_skills_df = get_all_skills()

    if all_skills_df.empty:
        st.warning("No skills found in the database. You can add skills later from your dashboard.")
        if st.button("Finish Registration →", type="primary"):
            st.session_state["reg_step"] = 1
            st.session_state["reg_emp_id"] = None
            st.success("Registration complete! Please log in.")
            st.switch_page("pages/login.py")
    else:
        # Group skills by category
        categories = sorted(all_skills_df["skill_category"].dropna().unique().tolist())
        if not categories:
            categories = ["General"]

        skill_entries = []  # list of (skill_id, skill_name, proficiency, years_exp)

        with st.form("skills_form"):
            st.markdown("For each category, select the skills you have and set your proficiency (1=Beginner → 5=Expert).")

            for cat in categories:
                cat_skills = all_skills_df[all_skills_df["skill_category"] == cat]
                st.markdown(f"**{cat}**")
                cols = st.columns(2)
                for i, (_, skill_row) in enumerate(cat_skills.iterrows()):
                    with cols[i % 2]:
                        selected = st.checkbox(skill_row["skill_name"], key=f"sk_{skill_row['skill_id']}")
                        if selected:
                            rc1, rc2 = st.columns(2)
                            with rc1:
                                prof = st.select_slider(
                                    f"Proficiency",
                                    options=[1, 2, 3, 4, 5],
                                    format_func=lambda x: PROFICIENCY_LABELS[x],
                                    value=3,
                                    key=f"prof_{skill_row['skill_id']}"
                                )
                            with rc2:
                                yrs = st.number_input(
                                    f"Years Exp",
                                    min_value=0.0, max_value=40.0,
                                    value=0.0, step=0.5,
                                    key=f"yrs_{skill_row['skill_id']}"
                                )
                            skill_entries.append((int(skill_row["skill_id"]), skill_row["skill_name"], prof, yrs))
                st.divider()

            col_skip, col_save = st.columns([1, 1])
            with col_skip:
                skip = st.form_submit_button("Skip for now")
            with col_save:
                save = st.form_submit_button("Save Skills & Finish →", type="primary")

        if save or skip:
            if save and skill_entries:
                saved = 0
                errors = []
                for skill_id, skill_name, prof, yrs in skill_entries:
                    try:
                        upsert_employee_skill(
                            emp_id=emp_id,
                            skill_id=skill_id,
                            proficiency=prof,
                            years_exp=yrs,
                            last_used=date.today().strftime("%Y-%m-%d"),
                            cert_status="None"
                        )
                        saved += 1
                    except Exception as e:
                        errors.append(f"{skill_name}: {e}")
                if errors:
                    st.warning(f"Saved {saved} skills. Some failed: {'; '.join(errors)}")
                else:
                    st.success(f"Saved {saved} skills!")

            # Reset step state and redirect
            st.session_state["reg_step"] = 1
            st.session_state["reg_emp_id"] = None
            st.success("Registration complete! Please log in.")
            st.switch_page("pages/login.py")
