from argon2 import PasswordHasher

MIN_ADMIN_PASSWORD_LENGTH = 12
MAX_ADMIN_PASSWORD_LENGTH = 128
_password_hasher = PasswordHasher()


class PasswordValidationError(ValueError):
    pass


def validate_admin_password(password: str) -> None:
    if not MIN_ADMIN_PASSWORD_LENGTH <= len(password) <= MAX_ADMIN_PASSWORD_LENGTH:
        raise PasswordValidationError(
            "Password must be between 12 and 128 characters."
        )


def hash_admin_password(password: str) -> str:
    validate_admin_password(password)
    return _password_hasher.hash(password)
