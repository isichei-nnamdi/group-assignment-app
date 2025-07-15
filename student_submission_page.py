# import streamlit as st
# import pandas as pd
# from datetime import datetime
# from io import BytesIO
# import base64

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

# import streamlit as st
# import pandas as pd
# from datetime import datetime
# import base64
# from googleapiclient.discovery import build
# from googleapiclient.http import MediaIoBaseUpload
# import io
# from io import BytesIO



# def student_submission_page(group_info, selected_course, student_email, client, sheet_id, creds):
#     st.markdown("---")
#     st.subheader("📤 Group Lab Submission")

#     group_name = group_info['group_name']
#     st.info(f"You're in **{group_name}** for the course **{selected_course}**")

#     # ===== Load Lab List =====
#     @st.cache_data
#     def load_lab_list(_client, _sheet_id):
#         try:
#             ws = _client.open_by_key(_sheet_id).worksheet("Labs")
#             return sorted(pd.Series(ws.col_values(1)).dropna().unique())
#         except Exception as e:
#             st.error(f"Unable to load lab list: {e}")
#             return []

#     lab_list = load_lab_list(client, sheet_id)
#     if not lab_list:
#         st.warning("No labs found for this course. Contact your instructor.")
#         return

#     selected_lab = st.selectbox("Select Lab to Submit", lab_list)

#     # ===== Load Submissions Sheet =====
#     def load_submissions_df(_client, _sheet_id):
#         try:
#             ws = _client.open_by_key(_sheet_id).worksheet("Submissions")
#         except:
#             ws = _client.open_by_key(_sheet_id).add_worksheet(title="Submissions", rows="1000", cols="10")
#             ws.append_row(["timestamp", "group_name", "course", "lab", "submitted_by", "file_name", "file_data", "graded", "grade"])

#         records = ws.get_all_values()
#         if len(records) > 1:
#             df = pd.DataFrame(records[1:], columns=records[0])
#         else:
#             df = pd.DataFrame(columns=[
#                 "timestamp", "group_name", "course", "lab",
#                 "submitted_by", "file_name", "file_data", "graded", "grade"
#             ])
#         return ws, df

#     # def upload_to_drive(file_bytes, filename, folder_id, creds):
#     #     try:
#     #         service = build("drive", "v3", credentials=creds)
    
#     #         file_metadata = {
#     #             "name": filename,
#     #             "parents": [folder_id]
#     #         }
#     #         media = MediaIoBaseUpload(BytesIO(file_bytes), mimetype="application/octet-stream")
    
#     #         # Upload the file
#     #         uploaded_file = service.files().create(
#     #             body=file_metadata,
#     #             media_body=media,
#     #             fields="id"
#     #         ).execute()
    
#     #         file_id = uploaded_file.get("id")
    
#     #         # Set permission to anyone with the link
#     #         permission = {
#     #             "type": "anyone",
#     #             "role": "reader"
#     #         }
#     #         service.permissions().create(
#     #             fileId=file_id,
#     #             body=permission
#     #         ).execute()
    
#     #         return f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
    
#     #     except Exception as e:
#     #         st.error(f"Drive upload failed: {e}")
#     #         return None
#     def upload_to_drive(file_bytes, filename, folder_id, creds):
#         try:
#             if not folder_id:
#                 raise ValueError("Drive folder ID is not provided!")
    
#             service = build("drive", "v3", credentials=creds)
    
#             file_metadata = {
#                 "name": filename,
#                 "parents": [folder_id]
#             }
    
#             media = MediaIoBaseUpload(BytesIO(file_bytes), mimetype="application/octet-stream")
    
#             uploaded_file = service.files().create(
#                 body=file_metadata,
#                 media_body=media,
#                 fields="id"
#             ).execute()
    
#             file_id = uploaded_file.get("id")
    
#             # Make file public
#             service.permissions().create(
#                 fileId=file_id,
#                 body={"type": "anyone", "role": "reader"},
#             ).execute()
    
#             return f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
    
#         except Exception as e:
#             st.error(f"🚫 Drive upload failed:\n\n**{e}**\n\n🔍 Check that your folder ID is correct and that your service account has access.")
#             return None

        
#     submissions_ws, submissions_df = load_submissions_df(client, sheet_id)

#     # Check for existing submission
#     existing = submissions_df[
#         (submissions_df["group_name"].str.lower() == group_name.lower()) &
#         (submissions_df["course"].str.lower() == selected_course.lower()) &
#         (submissions_df["lab"].str.lower() == selected_lab.lower())
#     ]

#     is_graded = not existing.empty and existing["graded"].iloc[0].strip().lower() == "yes"

#     if not existing.empty:
#         st.success(f"✅ Submission already made for {selected_lab}.")
#         st.write(f"**Submitted by:** {existing['submitted_by'].iloc[0]}")
#         st.write(f"**Filename:** {existing['file_name'].iloc[0]}")
        
#         file_link = existing['file_link'].iloc[0]
#         file_name = existing['file_name'].iloc[0]
#         file_extension = file_name.lower().split('.')[-1]
        
#         st.markdown(f"📄 **File Name:** {file_name}")
#         st.markdown(f"[🔗 View or Download File]({file_link})")
        
#         # Try to embed preview
#         if file_extension == "pdf":
#             # Embed PDF preview (works well)
#             preview_url = file_link.replace("/view?usp=drive_link", "/preview")
#             st.components.v1.iframe(preview_url, height=600)
        
#         elif file_extension in ["doc", "docx", "ppt", "pptx", "xls", "xlsx"]:
#             # Google Docs Viewer (only if file is a Google-converted doc)
#             preview_url = f"https://docs.google.com/gview?url={file_link}&embedded=true"
#             st.components.v1.iframe(preview_url, height=600)
        
#         elif file_extension == "ipynb":
#             # Jupyter Notebook viewer (via nbviewer)
#             from urllib.parse import quote
#             notebook_url = quote(file_link, safe='')
#             nbviewer_url = f"https://nbviewer.org/url/{notebook_url}"
#             st.markdown(f"[📘 View Notebook via nbviewer]({nbviewer_url})")
        
#         elif file_extension in ["png", "jpg", "jpeg", "gif"]:
#             st.image(file_link, caption=file_name, use_column_width=True)
        
#         else:
#             st.info("⚠️ Preview not supported for this file type. Please use the download link above.")


#         if is_graded:
#             st.info(f"📝 This submission has been graded: **{existing['grade'].iloc[0]}**")
#         else:
#             if st.button("🗑️ Delete Submission and Re-upload"):
#                 submissions_df = submissions_df.drop(existing.index)
#                 submissions_ws.clear()
#                 submissions_ws.append_row([
#                     "timestamp", "group_name", "course", "lab", "submitted_by",
#                     "file_name", "file_data", "graded", "grade"
#                 ])
#                 for _, row in submissions_df.iterrows():
#                     submissions_ws.append_row(list(row))
#                 st.success("Submission deleted. You can now re-upload.")
#                 st.rerun()
#     else:
#         uploaded = st.file_uploader("📎 Upload Lab Document (PDF/Docx)", type=["pdf", "docx", "ipynb", "py", "xlsx", "csv", "txt"])
#         if uploaded and st.button("Submit Lab Report"):
#             file_bytes = uploaded.read()
#             timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
#             # Upload to Drive
#             folder_id = st.secrets["google_service_account"]["drive_folder_id"]
#             drive_link = upload_to_drive(file_bytes, uploaded.name, folder_id, creds)

        
#             if not drive_link:
#                 st.error("❌ Could not upload the file.")
#                 return
        
#             # Save to Sheet
#             new_row = [
#                 timestamp, group_name, selected_course, selected_lab,
#                 student_email, uploaded.name, drive_link, "No", ""
#             ]
#             submissions_ws.append_row(new_row)
#             st.success("✅ Submission uploaded and saved!")
#             st.balloons()
#             st.rerun()


import streamlit as st
import pandas as pd
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from io import BytesIO


def student_submission_page(group_info, selected_course, student_email, client, sheet_id, creds):
    st.markdown("---")
    st.subheader("📤 Group Lab Submission")

    group_name = group_info['group_name']
    st.info(f"You're in **{group_name}** for the course **{selected_course}**")

    # ========== Load Labs ==========
    @st.cache_data
    def load_lab_list(_client, _sheet_id):
        try:
            ws = _client.open_by_key(_sheet_id).worksheet("Labs")
            return sorted(pd.Series(ws.col_values(1)).dropna().unique())
        except Exception as e:
            st.error(f"Unable to load lab list: {e}")
            return []

    lab_list = load_lab_list(client, sheet_id)
    if not lab_list:
        st.warning("No labs found for this course.")
        return

    selected_lab = st.selectbox("Select Lab to Submit", lab_list)

    # ========== Load Submissions ==========
    def load_submissions_df(_client, _sheet_id):
        try:
            ws = _client.open_by_key(_sheet_id).worksheet("Submissions")
        except:
            ws = _client.open_by_key(_sheet_id).add_worksheet(title="Submissions", rows="1000", cols="10")
            ws.append_row(["timestamp", "group_name", "course", "lab", "submitted_by", "file_name", "file_link", "graded", "grade"])

        records = ws.get_all_values()
        df = pd.DataFrame(records[1:], columns=records[0]) if len(records) > 1 else pd.DataFrame(columns=[
            "timestamp", "group_name", "course", "lab", "submitted_by",
            "file_name", "file_link", "graded", "grade"
        ])
        return ws, df

    # ========== Upload to Google Drive ==========
    def upload_to_drive(file_bytes, filename, folder_id, creds):
        try:
            service = build("drive", "v3", credentials=creds)
            file_metadata = {"name": filename, "parents": [folder_id]}
            media = MediaIoBaseUpload(BytesIO(file_bytes), mimetype="application/octet-stream")
            uploaded_file = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
            file_id = uploaded_file.get("id")

            # Set permissions
            permission = {"type": "anyone", "role": "reader"}
            service.permissions().create(fileId=file_id, body=permission).execute()

            return f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
        except Exception as e:
            st.error(f"Drive upload failed: {e}")
            return None

    # Load submission data
    submissions_ws, submissions_df = load_submissions_df(client, sheet_id)

    # Check for existing submission
    existing = submissions_df[
        (submissions_df["group_name"].str.lower() == group_name.lower()) &
        (submissions_df["course"].str.lower() == selected_course.lower()) &
        (submissions_df["lab"].str.lower() == selected_lab.lower())
    ]

    # If already submitted
    if not existing.empty:
        st.success(f"✅ Submission already made for {selected_lab}.")
        submitted_by = existing['submitted_by'].iloc[0]
        file_name = existing['file_name'].iloc[0]
        file_link = existing['file_link'].iloc[0]
        grade = existing['grade'].iloc[0]
        graded_status = existing['graded'].iloc[0].strip().lower()

        st.markdown(f"📎 **File:** [{file_name}]({file_link})")
        st.markdown(f"👤 **Submitted by:** {submitted_by}")

        if graded_status == "yes":
            st.success(f"📝 This submission has been graded: **{grade}**")
        else:
            if st.button("🗑️ Delete Submission and Re-upload"):
                submissions_df = submissions_df.drop(existing.index)
                submissions_ws.clear()
                submissions_ws.append_row(submissions_df.columns.tolist())
                for _, row in submissions_df.iterrows():
                    submissions_ws.append_row(list(row))
                st.success("Deleted. You can now re-upload.")
                st.rerun()

    # If not submitted yet
    else:
        uploaded = st.file_uploader("📎 Upload Lab Document", type=["pdf", "docx", "ipynb", "py", "xlsx", "csv", "txt"])
        if uploaded and st.button("Submit Lab Report"):
            file_bytes = uploaded.read()
            folder_id = st.secrets["google_service_account"]["drive_folder_id"]
            drive_link = upload_to_drive(file_bytes, uploaded.name, folder_id, creds)

            if not drive_link:
                st.error("❌ File upload failed.")
                return

            new_row = [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                group_name, selected_course, selected_lab,
                student_email, uploaded.name, drive_link, "No", ""
            ]
            submissions_ws.append_row(new_row)
            st.success("✅ Submission uploaded and saved!")
            st.balloons()
            st.rerun()

