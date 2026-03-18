import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
import plotly.express as px
import pandas as pd
from datetime import date, datetime
from utils.auth import require_login
from utils.db import (
    get_employee_by_id, get_employee_skills, get_employee_performance,
    get_employee_training, get_open_jobs, get_job_required_skills,
    get_career_interests, upsert_career_interest, mark_applied, upsert_match,
    get_all_skills, upsert_employee_skill, run_query
)
from utils.ml_engine import (
    compute_skill_match, compute_experience_match,
    compute_performance_match, compute_growth_potential,
    compute_overall_match, skill_gap_analysis
)

st.set_page_config(page_title="My Dashboard", page_icon="👤", layout="wide")
require_login()

emp_id = st.session_state["employee_id"]
emp_df = get_employee_by_id(emp_id)
if emp_df.empty:
    st.error("Employee record not found.")
    st.stop()

emp = emp_df.iloc[0]
emp_skills = get_employee_skills(emp_id)
perf_df = get_employee_performance(emp_id)
training_df = get_employee_training(emp_id)
jobs_df = get_open_jobs()

# ── Helper: years of experience ───────────────────────────────────────────────
def calc_years(hire_date):
    if not hire_date:
        return 0
    if hasattr(hire_date, "year"):
        return (date.today() - hire_date).days / 365.25
    try:
        return (date.today() - datetime.strptime(str(hire_date), "%Y-%m-%d").date()).days / 365.25
    except Exception:
        return 0

yrs_exp = calc_years(emp.get("hire_date"))

# ── Helper: certification/course recommendations ──────────────────────────────
CERT_RECOMMENDATIONS = {
    "Python":        ["Python Institute PCEP/PCAP", "Coursera: Python for Everybody"],
    "SQL":           ["Oracle SQL Certification", "Mode Analytics SQL Tutorial"],
    "Machine Learning": ["Google ML Crash Course", "Coursera: ML Specialization (Andrew Ng)"],
    "Data Analysis": ["IBM Data Analyst Certificate", "DataCamp: Data Analyst Track"],
    "Java":          ["Oracle Java SE Certification", "Udemy: Java Masterclass"],
    "JavaScript":    ["freeCodeCamp JS Certification", "Udemy: The Complete JS Course"],
    "React":         ["Meta Front-End Developer Certificate", "Scrimba React Course"],
    "AWS":           ["AWS Cloud Practitioner", "AWS Solutions Architect Associate"],
    "Docker":        ["Docker Certified Associate", "KodeKloud Docker Course"],
    "Kubernetes":    ["CKA (Certified Kubernetes Admin)", "Linux Foundation K8s Course"],
    "Project Management": ["PMP Certification", "Google Project Management Certificate"],
    "Communication": ["Toastmasters", "Coursera: Improving Communication Skills"],
    "Leadership":    ["CCL Leadership Development", "LinkedIn Learning: Leadership Foundations"],
}

def get_recommendations(skill_name: str) -> list:
    for key, recs in CERT_RECOMMENDATIONS.items():
        if key.lower() in skill_name.lower():
            return recs
    return [f"Search Coursera/Udemy for '{skill_name}'", f"Look for '{skill_name}' certification on LinkedIn Learning"]

# ── Helper: build match detail explanation ────────────────────────────────────
def build_match_explanation(m: dict, job_row, emp_skills_df: pd.DataFrame) -> dict:
    job_skills_df = m["job_skills_df"]
    gap_df = skill_gap_analysis(emp_skills_df, job_skills_df) if not job_skills_df.empty else pd.DataFrame()

    skill_pct = m["skill"]
    exp_pct   = m["experience"]
    perf_pct  = m["performance"]
    growth_pct = m["growth"]

    # Skill explanation
    if not gap_df.empty:
        matched = gap_df[gap_df["gap"] == 0]
        gaps    = gap_df[gap_df["gap"] > 0]
        if not emp_skills_df.empty:
            missing = job_skills_df[~job_skills_df["skill_id"].isin(emp_skills_df["skill_id"].tolist())]
        else:
            missing = job_skills_df
        skill_why = f"You match {len(matched)}/{len(gap_df)} required skills fully."
        if not gaps.empty:
            skill_why += f" {len(gaps)} skill(s) need improvement."
        if not missing.empty:
            skill_why += f" {len(missing)} skill(s) are missing entirely."
    else:
        skill_why = "No specific skills required for this role — default score applied."

    # Experience explanation
    req_min = job_row.get("min_experience", 0) or 0
    req_max = job_row.get("max_experience", 20) or 20
    if yrs_exp < req_min:
        exp_why = f"You have {yrs_exp:.1f} yrs but role needs {req_min}+ yrs. Score reduced proportionally."
    elif yrs_exp <= req_max:
        exp_why = f"Your {yrs_exp:.1f} yrs falls within the {req_min}–{req_max} yr range. Full score."
    else:
        exp_why = f"You have {yrs_exp:.1f} yrs which exceeds the {req_max} yr max. Slight reduction applied."

    # Performance explanation
    if not perf_df.empty:
        avg = perf_df["performance_rating"].astype(float).mean()
        perf_why = f"Your average performance rating is {avg:.1f}/5, giving {perf_pct:.0f}%."
    else:
        perf_why = "No performance reviews on record — default score of 60% applied."

    # Growth explanation
    if not perf_df.empty:
        latest_potential = str(perf_df.iloc[0].get("potential_rating", ""))
        growth_why = f"Latest potential rating: '{latest_potential}'. Training records: {len(training_df)}."
    else:
        growth_why = "No performance/training data — default growth score applied."

    # Recommendations for gaps
    recs = []
    if not gap_df.empty:
        for _, sk in gap_df[gap_df["gap"] > 0].iterrows():
            for r in get_recommendations(sk["skill_name"]):
                recs.append((sk["skill_name"], r))
        if not emp_skills_df.empty:
            missing_skills = job_skills_df[~job_skills_df["skill_id"].isin(emp_skills_df["skill_id"].tolist())]
        else:
            missing_skills = job_skills_df
        for _, sk in missing_skills.iterrows():
            for r in get_recommendations(sk["skill_name"]):
                recs.append((sk["skill_name"], r))

    return {
        "skill_why": skill_why,
        "exp_why": exp_why,
        "perf_why": perf_why,
        "growth_why": growth_why,
        "gap_df": gap_df,
        "recs": recs,
    }

# ── Check if already applied ──────────────────────────────────────────────────
def get_applied_job_ids(emp_id: int) -> set:
    try:
        df = run_query(
            "SELECT job_id FROM match_results WHERE employee_id = %s AND employee_applied = TRUE",
            (emp_id,)
        )
        return set(df["job_id"].tolist()) if not df.empty else set()
    except Exception:
        return set()

applied_job_ids = get_applied_job_ids(emp_id)

st.title(f"👤 Welcome, {emp['full_name']}")
st.caption(f"{emp['current_role']} · {emp['current_department']} · {emp['location']}")

col1, col2, col3, col4 = st.columns(4)
col1.metric("My Skills", len(emp_skills))
col2.metric("Avg Performance", f"{perf_df['performance_rating'].mean():.1f}/5" if not perf_df.empty else "N/A")
col3.metric("Trainings", len(training_df))
col4.metric("Open Positions", len(jobs_df))

st.divider()

tab1, tab2, tab3, tab4, tab5 = st.tabs(["🎯 Job Matches", "🛠 My Skills", "➕ Manage Skills", "📈 Performance", "🌱 Career Goals"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Job Matches
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    if jobs_df.empty:
        st.info("No open positions at the moment.")
    else:
        job_matches = []
        for _, job in jobs_df.iterrows():
            job_skills_df = get_job_required_skills(int(job["job_id"]))
            skill_score  = compute_skill_match(emp_skills, job_skills_df)
            exp_score    = compute_experience_match(emp.to_dict(), job.to_dict())
            perf_score   = compute_performance_match(perf_df)
            growth_score = compute_growth_potential(perf_df, training_df)
            overall      = compute_overall_match(skill_score, exp_score, perf_score, growth_score)

            try:
                upsert_match(int(job["job_id"]), emp_id, {
                    "match_score": overall, "skill_match_score": skill_score,
                    "experience_match_score": exp_score, "performance_match_score": perf_score,
                    "growth_potential_score": growth_score,
                })
            except Exception:
                pass

            job_matches.append({
                "job_id": job["job_id"], "job_title": job["job_title"],
                "department": job["department"], "location": job["location"],
                "job_level": job.get("job_level", ""), "overall": overall,
                "skill": skill_score, "experience": exp_score,
                "performance": perf_score, "growth": growth_score,
                "job_skills_df": job_skills_df, "job_row": job,
            })

        job_matches.sort(key=lambda x: x["overall"], reverse=True)

        # Summary chart — only jobs ≥50%
        above_50 = [m for m in job_matches if m["overall"] >= 50]
        below_50 = [m for m in job_matches if m["overall"] < 50]

        if above_50:
            st.markdown(f"### 🔔 {len(above_50)} position(s) where you match 50%+")
            chart_df = pd.DataFrame([{"Job": m["job_title"], "Match %": m["overall"], "Department": m["department"]} for m in above_50])
            fig = px.bar(chart_df, x="Job", y="Match %", color="Department",
                         title="Your Top Matches (≥50%)", range_y=[0, 100])
            fig.update_layout(height=280)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No positions with 50%+ match yet. Update your skills to improve your score.")

        st.divider()
        st.markdown(f"**All {len(job_matches)} open positions:**")

        for m in job_matches:
            badge = "🟢" if m["overall"] >= 75 else ("🟡" if m["overall"] >= 50 else "🔴")
            is_applied = int(m["job_id"]) in applied_job_ids
            applied_tag = "  ✅ Applied" if is_applied else ""
            new_tag = "  🆕 NEW" if m["overall"] >= 50 else ""

            with st.expander(f"{badge} **{m['job_title']}** — {m['department']} | {m['job_level']} | {m['location']}   {m['overall']:.0f}%{applied_tag}{new_tag}"):
                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.metric("Overall", f"{m['overall']:.0f}%")
                mc2.metric("Skill Match", f"{m['skill']:.0f}%")
                mc3.metric("Experience", f"{m['experience']:.0f}%")
                mc4.metric("Performance", f"{m['performance']:.0f}%")

                # Detail button
                detail_key = f"detail_{m['job_id']}"
                if detail_key not in st.session_state:
                    st.session_state[detail_key] = False

                col_det, col_app = st.columns([1, 1])
                with col_det:
                    if st.button("🔍 Why this score?", key=f"why_{m['job_id']}"):
                        st.session_state[detail_key] = not st.session_state[detail_key]
                with col_app:
                    if is_applied:
                        st.button("✅ Already Applied", key=f"app_{m['job_id']}", disabled=True)
                    else:
                        if st.button("Apply Now", key=f"app_{m['job_id']}", type="primary"):
                            try:
                                mark_applied(int(m["job_id"]), emp_id)
                                applied_job_ids.add(int(m["job_id"]))
                                st.success("Application submitted!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Could not apply: {e}")

                if st.session_state[detail_key]:
                    expl = build_match_explanation(m, m["job_row"], emp_skills)
                    st.divider()
                    st.markdown("#### Score Breakdown")

                    d1, d2, d3, d4 = st.columns(4)
                    with d1:
                        st.markdown(f"**Skill ({m['skill']:.0f}%)**")
                        st.caption(expl["skill_why"])
                    with d2:
                        st.markdown(f"**Experience ({m['experience']:.0f}%)**")
                        st.caption(expl["exp_why"])
                    with d3:
                        st.markdown(f"**Performance ({m['performance']:.0f}%)**")
                        st.caption(expl["perf_why"])
                    with d4:
                        st.markdown(f"**Growth ({m['growth']:.0f}%)**")
                        st.caption(expl["growth_why"])

                    if not expl["gap_df"].empty:
                        st.markdown("#### Skills Analysis")
                        gap_df = expl["gap_df"]
                        left, right = st.columns([1, 1])
                        with left:
                            matched = gap_df[gap_df["gap"] == 0]
                            gaps    = gap_df[gap_df["gap"] > 0]
                            if not matched.empty:
                                st.markdown("✅ **Have:**")
                                for _, sk in matched.iterrows():
                                    st.markdown(f"- {sk['skill_name']} ({sk['employee_proficiency']}/5)")
                            if not gaps.empty:
                                st.markdown("⚠️ **Improve:**")
                                for _, sk in gaps.iterrows():
                                    st.markdown(f"- {sk['skill_name']}: {sk['employee_proficiency']}/5 → {sk['required_proficiency']}/5")
                            if not emp_skills.empty:
                                missing = m["job_skills_df"][~m["job_skills_df"]["skill_id"].isin(emp_skills["skill_id"].tolist())]
                            else:
                                missing = m["job_skills_df"]
                            if not missing.empty:
                                st.markdown("🆕 **Learn:**")
                                for _, sk in missing.iterrows():
                                    st.markdown(f"- {sk['skill_name']} (need L{sk.get('minimum_proficiency',1)})")

                        with right:
                            fig_gap = px.bar(
                                gap_df, x="skill_name",
                                y=["employee_proficiency", "required_proficiency"],
                                barmode="group",
                                color_discrete_map={"employee_proficiency": "#4F46E5", "required_proficiency": "#E11D48"},
                                labels={"value": "Level (1-5)", "skill_name": "Skill", "variable": ""},
                                title="Your Skills vs Required"
                            )
                            fig_gap.update_layout(height=260, margin=dict(t=40, b=10))
                            st.plotly_chart(fig_gap, use_container_width=True)

                    if expl["recs"]:
                        st.markdown("#### 📚 Recommended Courses & Certifications")
                        seen = set()
                        for skill_name, rec in expl["recs"]:
                            if rec not in seen:
                                st.markdown(f"- **{skill_name}:** {rec}")
                                seen.add(rec)

                    # How to improve overall score
                    st.markdown("#### 💡 How to improve your match")
                    tips = []
                    if m["skill"] < 70:
                        tips.append("Improve your skill proficiency levels in the required skills above.")
                    if m["experience"] < 70:
                        tips.append(f"Gain more experience — you have {yrs_exp:.1f} yrs, role needs {m['job_row'].get('min_experience',0)}+ yrs.")
                    if m["performance"] < 70:
                        tips.append("Work towards higher performance ratings in your next review cycle.")
                    if m["growth"] < 70:
                        tips.append("Complete more training courses to boost your growth potential score.")
                    if not tips:
                        tips.append("You're already a strong match! Apply now.")
                    for tip in tips:
                        st.markdown(f"- {tip}")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — My Skills (view)
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    emp_skills_view = get_employee_skills(emp_id)
    if emp_skills_view.empty:
        st.info("No skills on record yet. Use the 'Manage Skills' tab to add your skills.")
    else:
        fig_skills = px.bar(
            emp_skills_view.sort_values("proficiency_level", ascending=False),
            x="skill_name", y="proficiency_level", color="skill_category",
            title="Your Skill Proficiency",
            labels={"proficiency_level": "Proficiency (1-5)", "skill_name": "Skill"},
        )
        st.plotly_chart(fig_skills, use_container_width=True)
        st.dataframe(
            emp_skills_view[["skill_name", "skill_category", "proficiency_level", "years_experience", "certification_status"]],
            use_container_width=True
        )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Manage Skills
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Add / Update Your Skills")
    st.caption("Select skills, set proficiency and years of experience.")

    all_skills_df = get_all_skills()
    current_skills = get_employee_skills(emp_id)
    current_skill_ids = set(current_skills["skill_id"].tolist()) if not current_skills.empty else set()

    PROFICIENCY_LABELS = {1: "1 - Beginner", 2: "2 - Basic", 3: "3 - Intermediate", 4: "4 - Advanced", 5: "5 - Expert"}

    if all_skills_df.empty:
        st.warning("No skills found in the master skills table.")
    else:
        categories = sorted(all_skills_df["skill_category"].dropna().unique().tolist())

        with st.form("manage_skills_form"):
            skill_entries = []
            for cat in categories:
                cat_skills = all_skills_df[all_skills_df["skill_category"] == cat]
                st.markdown(f"**{cat}**")
                for _, skill_row in cat_skills.iterrows():
                    sid = int(skill_row["skill_id"])
                    existing_row = current_skills[current_skills["skill_id"] == sid] if not current_skills.empty else pd.DataFrame()
                    existing_prof = int(existing_row.iloc[0]["proficiency_level"]) if not existing_row.empty else 3
                    existing_yrs  = float(existing_row.iloc[0]["years_experience"]) if not existing_row.empty else 0.0

                    selected = st.checkbox(
                        skill_row["skill_name"],
                        value=(sid in current_skill_ids),
                        key=f"msk_{sid}"
                    )
                    if selected:
                        c1, c2 = st.columns(2)
                        with c1:
                            prof = st.select_slider(
                                f"Proficiency",
                                options=[1, 2, 3, 4, 5],
                                format_func=lambda x: PROFICIENCY_LABELS[x],
                                value=existing_prof,
                                key=f"mprof_{sid}"
                            )
                        with c2:
                            yrs = st.number_input(
                                f"Years of Experience",
                                min_value=0.0, max_value=40.0,
                                value=existing_yrs, step=0.5,
                                key=f"myrs_{sid}"
                            )
                        skill_entries.append((sid, skill_row["skill_name"], prof, yrs))
                st.divider()

            save_btn = st.form_submit_button("Save Skills", type="primary")

        if save_btn:
            saved, errors = 0, []
            for skill_id, skill_name, prof, yrs in skill_entries:
                try:
                    upsert_employee_skill(
                        emp_id=emp_id, skill_id=skill_id,
                        proficiency=prof, years_exp=yrs,
                        last_used=date.today().strftime("%Y-%m-%d"),
                        cert_status="None"
                    )
                    saved += 1
                except Exception as e:
                    errors.append(f"{skill_name}: {e}")
            if errors:
                st.warning(f"Saved {saved} skills. Errors: {'; '.join(errors)}")
            else:
                st.success(f"Saved {saved} skills successfully!")
            st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Performance
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    if perf_df.empty:
        st.info("No performance reviews on record.")
    else:
        fig_perf = px.line(
            perf_df.sort_values("review_date"), x="review_date", y="performance_rating",
            markers=True, title="Performance Over Time",
            labels={"performance_rating": "Rating (1-5)"},
        )
        st.plotly_chart(fig_perf, use_container_width=True)
        st.dataframe(
            perf_df[["review_date", "performance_rating", "potential_rating", "reviewer_notes"]],
            use_container_width=True
        )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — Career Goals
# ══════════════════════════════════════════════════════════════════════════════
with tab5:
    interests_df = get_career_interests(emp_id)
    existing = interests_df.iloc[0].to_dict() if not interests_df.empty else {}

    DEPARTMENTS = ["Engineering", "Product", "Design", "Marketing", "Sales", "HR", "Finance", "Operations"]
    TIMELINES   = ["0-6 months", "6-12 months", "1-2 years", "2+ years"]

    with st.form("career_goals_form"):
        dept_idx     = DEPARTMENTS.index(existing.get("interested_department")) if existing.get("interested_department") in DEPARTMENTS else 0
        timeline_idx = TIMELINES.index(existing.get("target_timeline")) if existing.get("target_timeline") in TIMELINES else 0
        dept     = st.selectbox("Target Department", DEPARTMENTS, index=dept_idx)
        role     = st.text_input("Target Role", value=existing.get("interested_role", ""))
        timeline = st.selectbox("Timeline", TIMELINES, index=timeline_idx)
        relocate = st.checkbox("Willing to Relocate", value=bool(existing.get("willing_to_relocate", False)))
        notes    = st.text_area("Notes", value=existing.get("notes", ""))
        if st.form_submit_button("Save Goals"):
            upsert_career_interest(emp_id, dept, role, timeline, relocate, notes)
            st.success("Career goals saved!")
