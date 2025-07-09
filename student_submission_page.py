# import streamlit as st
# import pandas as pd
# from datetime import datetime
# from io import BytesIO

# def student_submission_page(group_info, selected_course, student_email, client, sheet_id):
#     st.subheader("📝 Group Submission Page")

#     group_name = group_info["group_name"]
#     group_members = [email.strip().lower() for email in group_info["members"].split(",")]
#     member_names = group_info["member_names"]

#     # ===== Load Lab List =====
#     @st.cache_data
#     def load_lab_list():
#         try:
#             ws = client.open_by_key(sheet_id).worksheet("Labs")
#             return sorted(pd.Series(ws.col_values(1)).dropna().unique())
#         except Exception as e:
#             st.error(f"Unable to load lab list: {e}")
#             return []
    
#         lab_list = load_lab_list()
    
#         if not lab_list:
#             st.warning("No labs found for this course. Please check back later.")
#             return
    
#         # ===== Select Lab =====
#         selected_lab = st.selectbox("Select Lab to Submit", lab_list)
#         submission_key = f"{group_name}_{selected_course}_{selected_lab}".replace(" ", "_").lower()
    
#     # ===== Load Submissions Sheet =====
#     def load_submissions_df():
#         try:
#             ws = client.open_by_key(sheet_id).worksheet("Submissions")
#         except:
#             ws = client.open_by_key(sheet_id).add_worksheet(title="Submissions", rows="1000", cols="10")
#             ws.append_row(["timestamp", "group_name", "course", "lab", "submitted_by", "file_name", "file_data", "graded", "grade"])
    
#         records = ws.get_all_values()
    
#         if len(records) > 1:
#             df = pd.DataFrame(records[1:], columns=records[0])
#         else:
#             # Return an empty DataFrame with the correct columns
#             df = pd.DataFrame(columns=[
#                 "timestamp", "group_name", "course", "lab",
#                 "submitted_by", "file_name", "file_data", "graded", "grade"
#             ])
    
#         return ws, df


#     submissions_ws, submissions_df = load_submissions_df()
#     st.write("Submission Columns:", submissions_df.columns.tolist())

#     # ===== Check for Existing Submission =====
#     existing = submissions_df[
#         (submissions_df["group_name"].str.lower() == group_name.lower()) &
#         (submissions_df["course"].str.lower() == selected_course.lower()) &
#         (submissions_df["lab"].str.lower() == selected_lab.lower())
#     ]

#     is_graded = not existing.empty and existing["graded"].iloc[0].strip().lower() == "yes"

#     if not existing.empty:
#         st.success(f"✅ Submission already made for {selected_lab} by {existing['submitted_by'].iloc[0]}")
#         st.write("**File Name:**", existing["file_name"].iloc[0])
#         st.write("**Submitted At:**", existing["timestamp"].iloc[0])
#         if is_graded:
#             st.info(f"🟢 Grade: **{existing['grade'].iloc[0]}**")
#         else:
#             if st.button("❌ Delete Submission (Only allowed before grading)"):
#                 all_values = submissions_ws.get_all_values()
#                 for i, row in enumerate(all_values[1:], start=2):  # skip header
#                     if (
#                         row[1].strip().lower() == group_name.lower() and
#                         row[2].strip().lower() == selected_course.lower() and
#                         row[3].strip().lower() == selected_lab.lower()
#                     ):
#                         submissions_ws.delete_rows(i)
#                         st.success("Submission deleted. You can re-upload now.")
#                         st.rerun()

#     if is_graded:
#         st.warning("This lab has been graded. You can no longer modify your submission.")
#         return

#     # ===== Upload New Submission =====
#     uploaded_file = st.file_uploader("📤 Upload Lab Document (PDF, DOCX, ZIP)", type=["pdf", "docx", "zip"])
#     if uploaded_file:
#         file_bytes = uploaded_file.getvalue()
#         file_name = uploaded_file.name

#         if st.button("🚀 Submit Lab"):
#             timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#             new_row = [
#                 timestamp,
#                 group_name,
#                 selected_course,
#                 selected_lab,
#                 student_email,
#                 file_name,
#                 file_bytes.hex(),  # Store as hex string for GSheet
#                 "No",
#                 ""
#             ]
#             submissions_ws.append_row(new_row)
#             st.success("Lab submitted successfully!")
#             st.rerun()

#     # ===== Optional Preview (for text files only) =====
#     if uploaded_file and uploaded_file.type.startswith("text/"):
#         content = uploaded_file.read().decode("utf-8")
#         st.text_area("Preview Content", value=content, height=300)

import streamlit as st
import pandas as pd
from datetime import datetime
import base64


# def load_lab_list(client, sheet_id):
#     try:
#         ws = client.open_by_key(sheet_id).worksheet("Labs")
#         return sorted(pd.Series(ws.col_values(1)).dropna().unique())
#     except Exception as e:
#         st.error(f"Failed to load lab list: {e}")
#         return []


# def load_submissions_df(client, sheet_id):
#     try:
#         ws = client.open_by_key(sheet_id).worksheet("Submissions")
#     except:
#         ws = client.open_by_key(sheet_id).add_worksheet(title="Submissions", rows="1000", cols="10")
#         ws.append_row([
#             "timestamp", "group_name", "course", "lab", "submitted_by",
#             "file_name", "file_data", "graded", "grade"
#         ])
#     df = pd.DataFrame(ws.get_all_records())
#     return ws, df
 # ===== Load Lab List =====
@st.cache_data
def load_lab_list():
    try:
        ws = client.open_by_key(sheet_id).worksheet("Labs")
        return sorted(pd.Series(ws.col_values(1)).dropna().unique())
    except Exception as e:
        st.error(f"Unable to load lab list: {e}")
        return []

    lab_list = load_lab_list()

    if not lab_list:
        st.warning("No labs found for this course. Please check back later.")
        return

    # ===== Select Lab =====
    selected_lab = st.selectbox("Select Lab to Submit", lab_list)
    submission_key = f"{group_name}_{selected_course}_{selected_lab}".replace(" ", "_").lower()

# ===== Load Submissions Sheet =====
def load_submissions_df():
    try:
        ws = client.open_by_key(sheet_id).worksheet("Submissions")
    except:
        ws = client.open_by_key(sheet_id).add_worksheet(title="Submissions", rows="1000", cols="10")
        ws.append_row(["timestamp", "group_name", "course", "lab", "submitted_by", "file_name", "file_data", "graded", "grade"])

    records = ws.get_all_values()

    if len(records) > 1:
        df = pd.DataFrame(records[1:], columns=records[0])
    else:
        # Return an empty DataFrame with the correct columns
        df = pd.DataFrame(columns=[
            "timestamp", "group_name", "course", "lab",
            "submitted_by", "file_name", "file_data", "graded", "grade"
        ])

    return ws, df


def student_submission_page(group_info, selected_course, student_email, client, sheet_id):
    st.markdown("---")
    st.subheader("📤 Group Lab Submission")

    group_name = group_info['group_name']
    st.info(f"You're in **{group_name}** for the course **{selected_course}**")

    lab_list = load_lab_list(client, sheet_id)
    if not lab_list:
        st.warning("No labs found for this course. Contact your instructor.")
        return

    selected_lab = st.selectbox("Select Lab to Submit", lab_list)

    # Load submissions
    submissions_ws, submissions_df = load_submissions_df(client, sheet_id)

    # Check for existing submission for this group/course/lab
    existing = submissions_df[
        (submissions_df["group_name"].str.lower() == group_name.lower()) &
        (submissions_df["course"].str.lower() == selected_course.lower()) &
        (submissions_df["lab"].str.lower() == selected_lab.lower())
    ]

    is_graded = not existing.empty and existing["graded"].iloc[0].strip().lower() == "yes"

    if not existing.empty:
        st.success(f"✅ Submission already made for {selected_lab}.")
        st.write(f"**Submitted by:** {existing['submitted_by'].iloc[0]}")
        st.write(f"**Filename:** {existing['file_name'].iloc[0]}")

        # Provide download option
        file_data = base64.b64decode(existing['file_data'].iloc[0].encode())
        st.download_button("📥 Download Submitted File", file_data, file_name=existing['file_name'].iloc[0])

        if is_graded:
            st.info(f"📝 This submission has been graded: **{existing['grade'].iloc[0]}**")
        else:
            if st.button("🗑️ Delete Submission and Re-upload"):
                # Remove existing row and save df back
                submissions_df = submissions_df.drop(existing.index)
                submissions_ws.clear()
                submissions_ws.append_row([
                    "timestamp", "group_name", "course", "lab", "submitted_by",
                    "file_name", "file_data", "graded", "grade"
                ])
                for _, row in submissions_df.iterrows():
                    submissions_ws.append_row(list(row))
                st.success("Submission deleted. You can now re-upload.")
                st.experimental_rerun()
    else:
        uploaded = st.file_uploader("📎 Upload Lab Document (PDF/Docx)", type=["pdf", "docx"])

        if uploaded and st.button("Submit Lab Report"):
            file_bytes = uploaded.read()
            encoded = base64.b64encode(file_bytes).decode()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            new_row = [
                timestamp, group_name, selected_course, selected_lab,
                student_email, uploaded.name, encoded, "No", ""
            ]

            submissions_ws.append_row(new_row)
            st.success("✅ Submission uploaded successfully!")
            st.experimental_rerun()
