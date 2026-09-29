"""Request and response bodies for the identity API."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StringConstraints

PASSWORD_MIN_LENGTH = 12
# Bounded so that hashing attacker-supplied input stays cheap.
PASSWORD_MAX_LENGTH = 128

NormalizedEmail = Annotated[EmailStr, AfterValidator(str.lower)]
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
NewPassword = Annotated[str, Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)]


class RegisterRequest(BaseModel):
    invite_code: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
    ]
    email: NormalizedEmail
    display_name: DisplayName
    password: NewPassword


class LoginRequest(BaseModel):
    email: NormalizedEmail
    password: Annotated[str, Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    created_at: datetime
