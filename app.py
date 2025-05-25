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
            creds = Credentials(
                token=access_token,
                refresh_token=token_data.get('refresh_token'),
                token_uri=TOKEN_URL,
                client_id=CLIENT_ID,
                client_secret=CLIENT_SECRET,
                scopes=SCOPE.split()
            )
            try:
                 st.session_state["credentials"] = creds
                 st.rerun()
            except Exception as e:
                 st.error(f"Error creating credentials: {e}")
                 st.json(token_data) # Show what we tried to use

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

# Main app
st.title("Job Annotation Tool")

# File selection
st.header("Step 1: Select File")

try:
    files = list_drive_files(st.session_state.service, "mimeType='text/csv'")

    if not files:
        st.warning("No CSV files found in your Google Drive.")
        st.stop()

    file_options = {f"{file['name']} ({file['id']})": file['id'] for file in files}

    # Set default index for selectbox
    current_selection_key = None
    if st.session_state.selected_file_id:
        for key, val_id in file_options.items():
            if val_id == st.session_state.selected_file_id:
                current_selection_key = key
                break
    
    default_index = 0
    if current_selection_key:
        try:
           default_index = list(file_options.keys()).index(current_selection_key)
        except ValueError:
            pass # Keep default index 0 if the old file is not found


    selected_file_name = st.selectbox(
        "Select a CSV file to annotate",
        options=list(file_options.keys()),
        index=default_index
    )

    selected_file_id = file_options[selected_file_name]

    if st.button("Load File") or (st.session_state.selected_file_id != selected_file_id):
        st.session_state.selected_file_id = selected_file_id
        st.session_state.selected_file = selected_file_name # Store name too if needed
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
    # More specific error handling could be added here


# Annotation interface
if st.session_state.df is not None:
    st.header("Step 2: Annotate Jobs")

    df = st.session_state.df
    current_index = st.session_state.current_index
    selected_file_id = st.session_state.selected_file_id # Get the ID here

    # Find the next unannotated row
    next_unannotated_index = -1
    for i in range(current_index, len(df)):
        if pd.isna(df.loc[i, 'finalAnnotation']):
            next_unannotated_index = i
            break
            
    # If no unannotated found from current_index, check from beginning
    if next_unannotated_index == -1:
         for i in range(0, current_index):
             if pd.isna(df.loc[i, 'finalAnnotation']):
                 next_unannotated_index = i
                 break

    if next_unannotated_index == -1:
        st.success("All jobs have been annotated!")
    else:
        st.session_state.current_index = next_unannotated_index
        current_index = next_unannotated_index # Update for display

        st.subheader(f"Job {current_index + 1} of {len(df)}")

        # Display job details (add checks in case columns are missing)
        st.markdown("### Title")
        st.write(df.loc[current_index, 'TITLE'] if 'TITLE' in df.columns else "N/A")

        st.markdown("### Company")
        st.write(df.loc[current_index, 'COMPANY_NAME'] if 'COMPANY_NAME' in df.columns else "N/A")

        st.markdown("### Description")
        st.write(df.loc[current_index, 'JOB_DESCRIPTION'] if 'JOB_DESCRIPTION' in df.columns else "N/A")

        # --- Annotation Function ---
        def annotate_and_save(annotation_value):
            df.loc[current_index, 'finalAnnotation'] = annotation_value
            st.session_state.df = df
            st.session_state.current_index = current_index + 1 # Move to next potential index
            try:
                csv_buffer = io.BytesIO(df.to_csv(index=False).encode())
                media = MediaIoBaseUpload(
                    csv_buffer,
                    mimetype='text/csv',
                    resumable=True
                )
                file = st.session_state.service.files().update(
                    fileId=selected_file_id,
                    media_body=media
                ).execute()
                st.toast("Progress saved!") # Use toast for less intrusive feedback
            except Exception as e:
                st.error(f"Error saving to Google Drive: {str(e)}")
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
        st.progress(progress)
        st.write(f"Progress: {annotated_count} / {total_count} ({progress*100:.1f}%)")


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

    if 'credentials' in st.session_state:
        if st.button("Logout"):
            # No token.pickle used, just clear session state
            keys_to_clear = list(st.session_state.keys())
            for key in keys_to_clear:
                del st.session_state[key]
            st.rerun()