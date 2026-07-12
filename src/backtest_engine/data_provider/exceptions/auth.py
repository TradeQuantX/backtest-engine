"""
Authentication-related exceptions.
"""

from backtest_engine.data_provider.exceptions.base import DataProviderError


class AuthError(DataProviderError):
    """Base authentication error."""
    pass


class TokenExpiredError(AuthError):
    """Access token has expired."""
    pass


class InvalidCredentialsError(AuthError):
    """Invalid API credentials provided."""
    pass


class OAuthFlowError(AuthError):
    """Error during OAuth flow (redirect, token exchange, etc.)."""
    pass


class TokenNotFoundError(AuthError):
    """No valid token found in storage."""
    pass


class TokenStorageError(AuthError):
    """Error reading/writing token storage."""
    pass


class InvalidTokenError(AuthError):
    """Token format is invalid or corrupted."""
    pass


class SessionInvalidatedError(AuthError):
    """Session was invalidated (user logged out elsewhere)."""
    pass