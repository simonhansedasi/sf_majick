import os
import requests
import time
import pandas as pd




class SalesforceAuth:
    def __init__(self):
        self.client_id = os.environ["SF_CLIENT_ID"]
        self.client_secret = os.environ["SF_CLIENT_SECRET"]
        self.refresh_token = os.environ["SF_REFRESH_TOKEN"]
        self.instance_url = os.environ["SF_INSTANCE_URL"]
        self.access_token = None
        self.expires_at = 0

    def refresh(self):
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
        }

        r = requests.post(
            "https://login.salesforce.com/services/oauth2/token",
            data=payload,
        )
        r.raise_for_status()

        data = r.json()
        self.access_token = data["access_token"]
        self.expires_at = time.time() + 50 * 60

    def headers(self):
        if not self.access_token or time.time() >= self.expires_at:
            self.refresh()

        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    
    
    
    
    
    
def SalesforceLogin():
    import requests
    from dotenv import load_dotenv
    import os

    load_dotenv()

    SF_CLIENT_ID = os.environ["SF_CLIENT_ID"]
    SF_CLIENT_SECRET = os.environ["SF_CLIENT_SECRET"]
    SF_REFRESH_TOKEN = os.environ["SF_REFRESH_TOKEN"]
    SF_INSTANCE_URL = os.environ["SF_INSTANCE_URL"]



    # use SalesforceAuth class to refresh access tokens automatically
    sf = SalesforceAuth()
    return sf








# def run_soql(soql_query, sf):
#     """
#     Run a SOQL query using sf_magic SalesforceAuth instance and return a pandas DataFrame.
#     Automatically strips 'attributes' field from Salesforce JSON records.
#     """
#     r = requests.get(
#         f"{sf.instance_url}/services/data/v59.0/query",
#         headers=sf.headers(),
#         params={"q": soql_query},
#     )
#     r.raise_for_status()
#     data = r.json()
    
#     records = data.get("records", [])
#     cleaned_records = [{k: v for k, v in rec.items() if k != "attributes"} for rec in records]
#     return pd.DataFrame(cleaned_records)

'''
For seeing occupied fields in salesforce
'''
def get_fields(sf, object_name):
    """
    Returns a list of all field names for a Salesforce object
    """
    url = f"{sf.instance_url}/services/data/v59.0/sobjects/{object_name}/describe"
    r = requests.get(url, headers=sf.headers())
    r.raise_for_status()
    describe = r.json()
    fields = [f["name"] for f in describe["fields"]]
    return fields

def get_non_empty_fields(sf, object_name, limit=200):
    # 1. Get all fields
    fields = get_fields(sf, object_name)
    
    # 2. Build SOQL query
    field_list = ",".join(fields)
    soql_query = f"SELECT {field_list} FROM {object_name} LIMIT {limit}"
    
    # 3. Run query
    records, df = run_soql(soql_query, sf)
    
    # 4. Determine which fields have at least 1 non-null value
    non_empty_fields = [col for col in df.columns if df[col].notnull().any()]
    
    return non_empty_fields





'''
for  building full field cheat sheets
'''
def get_object_fields(object_name, sf):
    """
    Fetch metadata for a Salesforce object and return as a pandas DataFrame.
    """
    r = requests.get(
        f"{sf.instance_url}/services/data/v59.0/sobjects/{object_name}/describe",
        headers=sf.headers(),
    )
    r.raise_for_status()
    
    describe = r.json
    
    data = r.json()
    
    fields = [
        {"name": f["name"], "label": f["label"], "type": f["type"]}
        for f in data.get("fields", [])
    ]
    return pd.DataFrame(fields)

def generate_md_cheatsheet(df_fields, object_name):
    """
    Generate a Markdown table of fields for a given Salesforce object.
    """
    md = f"# {object_name} Fields Cheatsheet\n\n"
    md += "| Field Name | Label | Type |\n"
    md += "|------------|-------|------|\n"
    
    for _, row in df_fields.iterrows():
        md += f"| {row['name']} | {row['label']} | {row['type']} |\n"
    
    return md




def run_soql(soql_query, sf):
    """
    Run a SOQL query using sf_magic SalesforceAuth instance and return a pandas DataFrame.
    Automatically strips 'attributes' field from Salesforce JSON records.
    """
    r = requests.get(
        f"{sf.instance_url}/services/data/v59.0/query",
        headers=sf.headers(),
        params={"q": soql_query},
    )
    r.raise_for_status()
    data = r.json()
    
    records = data.get("records", [])
    cleaned_records = [{k: v for k, v in rec.items() if k != "attributes"} for rec in records]
    return records, pd.DataFrame(cleaned_records)




