import os
import os.path
import json
import boto3
from dotenv import load_dotenv

load_dotenv()

ssmClient = boto3.client('ssm')

def get_secret(name):
    secret = os.getenv(name) or ssmClient.get_parameter(Name=name)['Parameter']['Value']
    return secret

class Settings:
    def __init__(self):
        self.envName = os.getenv("PYTHON_ENV")
        self.checkrBaseUrl = "https://api.checkr.com"
        self.checkrApiKey = get_secret("CHECKR_API_KEY")
        self.bimApiKey = get_secret("BIM_API_KEY")
        self.backgroundCheckTable = f'bim-{self.envName}-background-check'
        self.salesforceOrgID = get_secret("SALESFORCE_ORG_ID")
        self.salesforcePassword = get_secret("SALESFORCE_PASSWORD")
        self.salesforceClientSecret = get_secret("SALESFORCE_CLIENT_SECRET")
        if self.envName == "qa":
            self.checkrPackage = "tasker_standard"
            self.salesforceUsername = "admin@believeinme.org.partial"
            self.salesforceClientID = "3MVG9hq7jmfCuKffxV8EIa4PjxZF9kf_P4Y4jyAs7BFp3mS3Zsj8pGMHf6sPhlT13fwzVKftV6q6aJ48C8YBS"
            self.salesforceOAuthURL = "https://test.salesforce.com/services/oauth2/token"
        else:
            self.checkrPackage = "basic_criminal"   
            self.salesforceUsername = "admin@believeinme.org"
            self.salesforceClientID = "3MVG9LBJLApeX_PAp1crLR4Uf.sD2RcTLtigoHK9dqDg30ENE2AzrTBmeA8w9tgOtBSx316r4F.be2CJShBp4"
            self.salesforceOAuthURL = "https://login.salesforce.com/services/oauth2/token"
    
settings = Settings()
