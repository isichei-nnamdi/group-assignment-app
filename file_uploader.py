import streamlit as st
import pandas as pd
# ============================== NEW FEATURE: Group Submission ==============================
# if st.session_state.user_role == "student":
st.subheader("📤 Group Lab Submission")

# Load updated groups data
latest_data = st.session_state.groups_ws.get_all_values()
groups_df = pd.DataFrame(latest_data[1:], columns=latest_data[0]) if len(latest_data) > 1 else pd.DataFrame(columns=latest_data[0])

# Get the student's email and find their group
student_email = st.session_state.user_email.strip().lower()
student_group = groups_df[groups_df["members"].str.contains(student_email, case=False, na=False)]

if student_group.empty:
    st.warning("You are not part of any group. Please create or join a group before submission.")
    st.stop()

group_record = student_group.iloc[0]
group_name = group_record['group_name']
course = group_record['course']

# Load submissions data from worksheet
submission_data = st.session_state.submissions_ws.get_all_values()
if submission_data:
    submission_df = pd.DataFrame(submission_data[1:], columns=submission_data[0])
else:
    submission_df = pd.DataFrame(columns=["timestamp", "group_name", "course", "lab_title", "file_url", "submitted_by", "graded", "grade"])

# Check if the group already submitted for this course
existing_submission = submission_df[(submission_df['group_name'] == group_name) & (submission_df['course'].str.lower() == course.lower())]

# List of labs for the course
course_labs = st.session_state.labs_map.get(course, [])
selected_lab = st.selectbox("Select Lab to Submit", course_labs)

if not existing_submission.empty:
    st.success("✅ Your group has submitted for this course.")

    row = existing_submission.iloc[0]
    st.markdown(f"**Submitted Lab:** {row['lab_title']}")
    st.markdown(f"**File:** [Download Submission]({row['file_url']})")
    st.markdown(f"**Submitted By:** {row['submitted_by']}")
    st.markdown(f"**Grade:** {row['grade'] if row['graded'] == 'yes' else 'Not yet graded'}")

    if row['graded'].lower() != 'yes':
        with st.form("update_submission_form"):
            uploaded_file = st.file_uploader("Replace Submission File", type=["pdf", "docx", "zip"])
            submit_btn = st.form_submit_button("Re-upload")

        if submit_btn and uploaded_file:
            file_url = save_file_to_drive(uploaded_file, group_name, selected_lab)  # you must define this

            row_index = submission_df[(submission_df['group_name'] == group_name) & (submission_df['course'].str.lower() == course.lower())].index[0] + 2
            st.session_state.submissions_ws.update(f"E{row_index}", file_url)
            st.session_state.submissions_ws.update(f"A{row_index}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

            st.success("✅ Submission updated successfully!")
            st.rerun()
    else:
        st.info("Submission has been graded. You can no longer modify it.")
else:
    with st.form("new_submission_form"):
        uploaded_file = st.file_uploader("Upload Your Lab Submission", type=["pdf", "docx", "zip"])
        submit_btn = st.form_submit_button("Submit")

    if submit_btn:
        if not uploaded_file:
            st.warning("Please upload a file.")
            st.stop()

        file_url = save_file_to_drive(uploaded_file, group_name, selected_lab)  # define this function separately

        new_row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            group_name,
            course,
            selected_lab,
            file_url,
            student_email,
            "no",
            ""
        ]

        if submission_df.empty:
            st.session_state.submissions_ws.append_row(submission_df.columns.tolist())
        st.session_state.submissions_ws.append_row(new_row)

        st.success("✅ Submission successful!")
        st.rerun()
