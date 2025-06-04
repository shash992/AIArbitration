
# Job Annotation Tool

A Streamlit application for annotating job postings as AI or non-AI jobs, with Google Drive integration for file storage.

## Setup Instructions

### Local Development

1. **Install the required dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
2. **Get your Google OAuth credentials:**
   - Go to the [Google Cloud Console](https://console.cloud.google.com/)
   - Select your project
   - Go to "APIs & Services" > "Credentials"
   - Create OAuth 2.0 credentials (choose Web application)
   - Download the `credentials.json` file
   - Place `credentials.json` in your project directory (same folder as `app.py`)
3. **Run the application:**
   ```bash
   streamlit run app.py
   ```

### Deploying on Streamlit Cloud

1. **Push your code to GitHub.**
2. **Go to [Streamlit Cloud](https://streamlit.io/cloud) and create a new app.**
3. **Add your Google OAuth credentials to Streamlit secrets:**
   - Go to your app's settings > **Secrets**
   - Add a new secret with the key `credentials.json` and the value as your entire credentials JSON (including the curly braces `{}`), wrapped in triple quotes:
     ```toml
     credentials.json = """
     {
       "web": {
         "client_id": "YOUR_CLIENT_ID",
         "project_id": "your-project-id",
         ...
       }
     }
     """
     ```
   - Make sure there are no extra spaces or newlines before/after the key or value.
   - Save the changes and wait a minute for them to propagate.
4. **(Optional) In Google Cloud Console:**
   - Add your Streamlit app URL (e.g. `https://your-app-name.streamlit.app`) to the OAuth consent screen's authorized redirect URIs and JavaScript origins.
   - Add your email as a test user.
5. **Deploy or rerun your app.**

## Usage

1. Click "Login with Google" and authorize the app.
2. Select a CSV file from your Google Drive.
3. Annotate each job as "AI Job" or "Non-AI Job".
4. Progress is automatically saved after each annotation.

## Features

- Google Drive integration for file storage
- Clean, user-friendly interface
- Progress tracking
- Automatic saving
- Session persistence
- Sidebar with instructions

## File Format

The input CSV file should have the following columns:
- TITLE
- COMPANY_NAME
- JOB_DESCRIPTION

The app will automatically add a `finalAnnotation` column where:
- 1 = AI Job
- 0 = Non-AI Job
- Null = Not yet annotated

## Security Note

- Never commit your `credentials.json` to GitHub (it's in `.gitignore`)
- On Streamlit Cloud, always use the Secrets manager for credentials
- Restrict your OAuth credentials in Google Cloud Console
- Never share your credentials publicly 