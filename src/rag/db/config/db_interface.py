# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager

from sqlalchemy.orm import Session


class DatabaseProvider(ABC):
    """
    Any database provider must inherit the `DatabaseProvider`
    strictly made for concrete lifecycle and session boundary
    """

    @abstractmethod
    def startup(self) -> None:
        """
        init db engine + verify connection
        """

    @abstractmethod
    def check_connection(self) -> tuple[bool, str]:
        """
        check db connection by execute simple query

        Returns:
            boolean flag if connection is ok and any successful message
        """

    @abstractmethod
    def shutdown(self) -> None:
        """
        must trigger during app shutdown to close db connection
        """

    @abstractmethod
    def get_session(self) -> AbstractContextManager[Session]:
        """
        create db session for each request

        Returns:
            database session wrapped in abstract context manager
        """
