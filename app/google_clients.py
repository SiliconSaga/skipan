"""All Google client construction lives here; everything downstream takes injected clients."""
import google.auth
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/spreadsheets",
]


def get_credentials():
    creds, _ = google.auth.default(scopes=SCOPES)
    return creds


def build_sheets(creds):
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def make_model_factory(project_id: str, region: str):
    def factory(model_name: str):
        import vertexai
        from vertexai.generative_models import GenerativeModel

        vertexai.init(project=project_id, location=region)
        return GenerativeModel(model_name)

    return factory


def read_values(sheets, spreadsheet_id: str, a1_range: str):
    # num_retries covers transient socket/SSL failures on Google's side (stale keep-alive connections).
    result = sheets.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=a1_range).execute(num_retries=2)
    return result.get("values", [])
