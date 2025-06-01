import streamlit as st
import pandas as pd
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
import io
import os
import pickle
import json
from dotenv import load_dotenv
import base64
from pathlib import Path
from io import BytesIO
from streamlit_oauth import OAuth2Component
import threading

# Load environment variables
load_dotenv()


# Google Drive API setup
SCOPES = ['https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/drive.readonly']

AUTHORIZE_URL = st.secrets["google"]["authorize_url"]
TOKEN_URL = st.secrets["google"]["token_url"]
REFRESH_TOKEN_URL = st.secrets["google"]["token_url"] # Usually same as token_url
CLIENT_ID = st.secrets["google"]["client_id"]
CLIENT_SECRET = st.secrets["google"]["client_secret"]
REDIRECT_URI = st.secrets["google"]["redirect_uri"]
SCOPE = "https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/userinfo.email openid"

oauth2 = OAuth2Component(
    CLIENT_ID,
    CLIENT_SECRET,
    AUTHORIZE_URL,
    TOKEN_URL,
    REFRESH_TOKEN_URL
)

if 'credentials' not in st.session_state:
    result = oauth2.authorize_button(
        "Log in with Google",
        REDIRECT_URI,
        SCOPE,
        extras_params={"access_type": "offline", "prompt": "consent"}
    )

    if result:
        token_data = result.get("token", {})
        access_token = token_data.get("access_token")

        if access_token:
            # Construct Credentials object carefully, ensuring it includes refresh_token if available
            try:
                creds = Credentials(
                    token=access_token,
                    refresh_token=token_data.get('refresh_token'),
                    token_uri=TOKEN_URL,
                    client_id=CLIENT_ID,
                    client_secret=CLIENT_SECRET,
                    scopes=SCOPE.split()
                )
                st.session_state["credentials"] = creds
                st.rerun()
            except Exception as e:
                st.error(f"Error creating credentials: {e}")
                st.json(token_data)

        else:
            st.error("OAuth response missing 'access_token'. Full response:")
            st.json(result)


if 'credentials' in st.session_state:
    creds = st.session_state['credentials']
    # Check if token needs refreshing
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            st.session_state['credentials'] = creds
        except Exception as e:
            st.error(f"Error refreshing token: {e}. Please log in again.")
            del st.session_state['credentials']
            st.rerun()

    if 'credentials' in st.session_state: # Re-check after potential refresh/logout
        service = build('drive', 'v3', credentials=creds)
        st.session_state.authenticated = True
        st.session_state.service = service
    else:
        st.stop()
else:
    st.stop()


def list_drive_files(service, query=None):
    """List files in Google Drive."""
    try:
        results = service.files().list(
            pageSize=100,
            q=query,
            fields="nextPageToken, files(id, name, mimeType)"
        ).execute()
        return results.get('files', [])
    except Exception as e:
        st.error(f"Error listing files: {str(e)}")
        # Check for auth errors specifically
        if 'invalid_grant' in str(e).lower() or 'token has been expired' in str(e).lower():
            st.warning("Authentication error. Trying to re-authenticate...")
            if 'credentials' in st.session_state:
                del st.session_state['credentials']
            st.rerun()
        return []


def download_file_from_drive(file_id, service):
    """Download a file from Google Drive."""
    try:
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        fh.seek(0)
        return fh
    except Exception as e:
        st.error(f"Error downloading file: {str(e)}")
        return None

# --- Utility function for saving to Google Drive in a thread ---
def save_to_drive(df, file_id, service):
    try:
        csv_buffer = io.BytesIO(df.to_csv(index=False).encode())
        media = MediaIoBaseUpload(
            csv_buffer,
            mimetype='text/csv',
            resumable=True
        )
        file = service.files().update(
            fileId=file_id,
            media_body=media
        ).execute()
        st.toast("Progress saved!")  # Less intrusive feedback
    except Exception as e:
        st.error(f"Error saving to Google Drive: {str(e)}")


# Initialize session state
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'df' not in st.session_state:
    st.session_state.df = None
if 'current_index' not in st.session_state:
    st.session_state.current_index = 0
if 'selected_file' not in st.session_state:
    st.session_state.selected_file = None
if 'selected_file_id' not in st.session_state:
    st.session_state.selected_file_id = None
if 'annotation_times' not in st.session_state:
    st.session_state.annotation_times = []
if 'last_annotation_time' not in st.session_state:
    st.session_state.last_annotation_time = None

# Main app
st.title("Job Annotation Tool")

# File selection helper to extract file ID from Google Drive link or ID
def extract_file_id(url_or_id):
    import re
    match = re.search(r'/d/([a-zA-Z0-9_-]+)', url_or_id)
    if match:
        return match.group(1)
    if 'id=' in url_or_id:
        return url_or_id.split('id=')[1].split('&')[0]
    return url_or_id.strip()

# Sidebar
with st.sidebar:
    st.header("Instructions")
    st.markdown("""
    1.  Log in with Google (if not already).
    2.  Select a CSV file from your Google Drive.
    3.  Click 'Load File' to start.
    4.  For each job:
        * Review the title, company, and description.
        * Click 'AI Job' if the position requires AI skills.
        * Click 'Non-AI Job' if it doesn't.
    5.  Progress is automatically saved after each annotation.
    """)

    st.markdown("### Load File")
    input_link = st.text_input("Paste a Google Drive CSV file link or file ID")
    selected_file_id = extract_file_id(input_link) if input_link else None

    if st.button("Load File", type="primary") and selected_file_id:
        st.session_state.selected_file_id = selected_file_id
        st.session_state.selected_file = input_link # Store the link or ID
        try:
            file = download_file_from_drive(selected_file_id, st.session_state.service)
            if file:
                df = pd.read_csv(file)
                if 'finalAnnotation' not in df.columns:
                    df['finalAnnotation'] = pd.NA # Use pd.NA for better handling
                st.session_state.df = df
                st.session_state.current_index = 0
                st.success("File loaded successfully!")
                st.rerun()
        except Exception as e:
            st.error(f"Error during file selection/loading: {str(e)}")

    if 'credentials' in st.session_state:
        st.markdown(
            """
            <style>
                .logout-button {
                    position: fixed;
                    bottom: 10px;
                    left: 10px;
                    width: calc(20% - 20px);
                }
            </style>
            <div class="logout-button">
            """,
            unsafe_allow_html=True
        )
        if st.button("Logout"):
            keys_to_clear = list(st.session_state.keys())
            for key in keys_to_clear:
                del st.session_state[key]
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)


# Annotation interface
if st.session_state.df is not None:
    st.header("Annotate Jobs")

    df = st.session_state.df
    selected_file_id = st.session_state.selected_file_id # Get the ID here

    # Find the next unannotated row
    next_unannotated_index = -1
    for i in range(st.session_state.current_index, len(df)):
        if pd.isna(df.loc[i, 'finalAnnotation']):
            next_unannotated_index = i
            break
            
    # If no unannotated found from current_index, check from beginning
    if next_unannotated_index == -1:
         for i in range(0, st.session_state.current_index):
             if pd.isna(df.loc[i, 'finalAnnotation']):
                 next_unannotated_index = i
                 break

    if next_unannotated_index == -1:
        st.success("All jobs have been annotated!")
    else:
        st.session_state.current_index = next_unannotated_index
        i = st.session_state.current_index

        st.subheader(f"Job {i + 1} of {len(df)}")

        import streamlit.components.v1 as components

        # # Scroll to top on rerun (smooth scrolling)
        # components.html("""
        #     <script>
        #         window.scrollTo({ top: 0, behavior: 'smooth' });
        #     </script>
        # """, height=0)
        

        # Display job details (add checks in case columns are missing)
        st.markdown("### Title")
        st.write(df.loc[i, 'TITLE'] if 'TITLE' in df.columns else "N/A")

        st.markdown("### Company")
        st.write(df.loc[i, 'COMPANY_NAME'] if 'COMPANY_NAME' in df.columns else "N/A")

        description = df.loc[i, 'cleaned_jd'] if 'cleaned_jd' in df.columns else "N/A"
        st.markdown("### Description")
        st.write(description)
        # --- Copy Description Button (HTML/JS clipboard) ---
        components.html(f"""
            <button onclick="navigator.clipboard.writeText(`{description}`); 
                             this.innerText='✅ Copied!'; 
                             setTimeout(() => this.innerText='📋 Copy Description', 2000);"
                    style="margin-bottom: 10px; padding: 6px 12px; font-size: 14px; cursor: pointer;">
                📋 Copy Description
            </button>
        """, height=40)

        # Display RA label metadata
        if 'RA1_name' in df.columns and 'RA_Label1' in df.columns:
            ra1_label = df.loc[i, 'RA_Label1']
            ra1_name = df.loc[i, 'RA1_name']
            st.write(f"**{ra1_name}**: {ra1_label}")

        if 'RA2_name' in df.columns and 'RA_Label2' in df.columns:
            ra2_label = df.loc[i, 'RA_Label2']
            ra2_name = df.loc[i, 'RA2_name']
            st.write(f"**{ra2_name}**: {ra2_label}")

        # --- Annotation Function ---
        def annotate_and_save(annotation_value):
            import time
            now = time.time()
            if st.session_state.last_annotation_time is not None:
                elapsed = now - st.session_state.last_annotation_time
                st.session_state.annotation_times.append(elapsed)
            st.session_state.last_annotation_time = now

            df.loc[i, 'finalAnnotation'] = annotation_value
            st.session_state.df = df
            st.session_state.current_index = i + 1
            threading.Thread(
                target=save_to_drive,
                args=(df.copy(), selected_file_id, st.session_state.service),
                daemon=True
            ).start()
            st.rerun()


        # Annotation buttons
        col1, col2 = st.columns(2)

        with col1:
            if st.button("AI Job", type="primary", use_container_width=True):
                annotate_and_save(1)

        with col2:
            if st.button("Non-AI Job", use_container_width=True):
                annotate_and_save(0)

        # Progress bar
        annotated_count = df['finalAnnotation'].notna().sum()
        total_count = len(df)
        progress = (annotated_count / total_count) if total_count > 0 else 0
        if st.session_state.annotation_times:
            avg_time = sum(st.session_state.annotation_times) / len(st.session_state.annotation_times)
            st.write(f"⏱ Average time per annotation: {avg_time:.2f} seconds")
        st.progress(progress)
        st.write(f"Progress: {annotated_count} / {total_count} ({progress*100:.1f}%)")

        def preload_next_job():
            next_i = i + 1
            if next_i < len(df) and pd.isna(df.loc[next_i, 'finalAnnotation']):
                _ = df.loc[next_i]  # preload row

        threading.Thread(target=preload_next_job, daemon=True).start()