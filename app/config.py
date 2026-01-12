from pydantic_settings import BaseSettings
import base64

class Settings(BaseSettings):
    ADO_ORG: str
    ADO_PAT: str

    @property
    def ADO_PAT_BASIC(self) -> str:
        """
        Returns Base64 encoded Basic auth string for Azure DevOps
        Format: Basic <base64(:PAT)>
        """
        token = f":{self.ADO_PAT}"  # username is empty
        return base64.b64encode(token.encode()).decode()

settings = Settings()
