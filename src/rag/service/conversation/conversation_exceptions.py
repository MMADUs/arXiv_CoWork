# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT


class ConversationServiceError(Exception):
    """Base exception for conversation service failures."""


class ConversationValidationError(ConversationServiceError, ValueError):
    """Raised when conversation input is invalid."""


class ConversationNotFoundError(ConversationServiceError):
    """Raised when a requested conversation resource cannot be found."""
