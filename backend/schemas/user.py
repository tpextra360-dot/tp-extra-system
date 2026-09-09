from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date

class PaperMemberItem(BaseModel):
    full_name: str
    phone_number: str = Field(..., pattern=r"^[0-9]{9,10}$")
    upline_member_code: Optional[str] = None
    birth_date: Optional[date] = None
    is_consent_age: bool = False

class BulkImportRequest(BaseModel):
    members: List[PaperMemberItem]