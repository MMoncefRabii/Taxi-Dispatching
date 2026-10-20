import asyncio
import logging
import os
import sys
from unittest.mock import AsyncMock, Mock

import pytest
from argon2 import PasswordHasher

import scripts.bootstrap_platform_owner as bootstrap_script
from app.models import PlatformAuditLog, SuperAdmin


class AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback):
        return None


def mock_session(*scalar_results):
    session = Mock()
    session.scalar = AsyncMock(side_effect=scalar_results)
    session.execute = AsyncMock()
    session.add = Mock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    transaction = AsyncContext(session)
    session.begin = Mock(return_value=transaction)
    return session


def test_bootstrap_creates_hashed_owner_without_leaking_password(
    monkeypatch, capsys, caplog
):
    password = "a-strong-password-long-enough"
    lookup_session = mock_session(None)
    save_session = mock_session(None, None)
    sessions = iter([lookup_session, save_session])
    monkeypatch.setattr(bootstrap_script, "SessionLocal", lambda: next(sessions))
    monkeypatch.setattr(bootstrap_script, "engine", None)
    monkeypatch.setattr("builtins.input", Mock(return_value="OWNER@example.com"))
    monkeypatch.setattr(
        bootstrap_script.getpass,
        "getpass",
        Mock(side_effect=[password, password]),
    )

    with caplog.at_level(logging.DEBUG):
        asyncio.run(bootstrap_script.bootstrap_from_prompt())

    output = capsys.readouterr().out
    owner = save_session.add.call_args.args[0]
    assert isinstance(owner, SuperAdmin)
    assert owner.email == "owner@example.com"
    assert owner.password_hash != password
    assert PasswordHasher().verify(owner.password_hash, password)
    assert "Created platform owner owner@example.com." in output
    assert password not in output
    assert password not in caplog.text
    assert owner.password_hash not in caplog.text


def test_second_run_is_noop_without_password_prompt(monkeypatch, capsys):
    existing_session = mock_session("existing-owner-id")
    monkeypatch.setattr(
        bootstrap_script,
        "SessionLocal",
        lambda: existing_session,
    )
    monkeypatch.setattr(bootstrap_script, "engine", None)
    monkeypatch.setattr("builtins.input", Mock(return_value="owner@example.com"))
    monkeypatch.setattr(
        bootstrap_script.getpass,
        "getpass",
        Mock(side_effect=AssertionError("existing owner must not prompt")),
    )

    asyncio.run(bootstrap_script.bootstrap_from_prompt())

    assert capsys.readouterr().out == (
        "Platform owner owner@example.com already exists; no changes made.\n"
    )
    bootstrap_script.getpass.getpass.assert_not_called()


def test_environment_password_is_consumed_without_printing_it(
    monkeypatch, capsys, caplog
):
    password = "one-command-environment-password"
    lookup_session = mock_session(None)
    save_session = mock_session(None, None)
    sessions = iter([lookup_session, save_session])
    monkeypatch.setattr(bootstrap_script, "SessionLocal", lambda: next(sessions))
    monkeypatch.setattr(bootstrap_script, "engine", None)
    monkeypatch.setenv(bootstrap_script.PASSWORD_ENV_VAR, password)

    with caplog.at_level(logging.DEBUG):
        asyncio.run(
            bootstrap_script.bootstrap_from_prompt(email="owner@example.com")
        )

    output = capsys.readouterr().out
    assert bootstrap_script.PASSWORD_ENV_VAR not in os.environ
    assert password not in output
    assert password not in caplog.text
    assert save_session.add.call_args.args[0].password_hash != password


def test_mismatched_password_confirmation_aborts_before_insert(monkeypatch):
    lookup_session = mock_session(None)
    monkeypatch.setattr(bootstrap_script, "SessionLocal", lambda: lookup_session)
    monkeypatch.setattr(bootstrap_script, "engine", None)
    monkeypatch.setattr("builtins.input", Mock(return_value="owner@example.com"))
    monkeypatch.setattr(
        bootstrap_script.getpass,
        "getpass",
        Mock(side_effect=["first-password-long-enough", "different-password"]),
    )

    with pytest.raises(bootstrap_script.BootstrapError, match="Passwords do not match"):
        asyncio.run(bootstrap_script.bootstrap_from_prompt())


def test_weak_password_is_rejected_before_insert(monkeypatch):
    lookup_session = mock_session(None)
    monkeypatch.setattr(bootstrap_script, "SessionLocal", lambda: lookup_session)
    monkeypatch.setattr(bootstrap_script, "engine", None)
    monkeypatch.setattr("builtins.input", Mock(return_value="owner@example.com"))
    monkeypatch.setattr(
        bootstrap_script.getpass,
        "getpass",
        Mock(side_effect=["short", "short"]),
    )

    with pytest.raises(bootstrap_script.PasswordValidationError):
        asyncio.run(bootstrap_script.bootstrap_from_prompt())


def test_reset_requires_explicit_confirmation_and_audits(monkeypatch, capsys):
    password = "a-new-strong-password-long-enough"
    owner = SuperAdmin(
        id="existing-owner-id",
        email="owner@example.com",
        password_hash="old-hash",
        active=True,
    )
    lookup_session = mock_session("existing-owner-id")
    save_session = mock_session(owner)
    sessions = iter([lookup_session, save_session])
    monkeypatch.setattr(bootstrap_script, "SessionLocal", lambda: next(sessions))
    monkeypatch.setattr(bootstrap_script, "engine", None)
    monkeypatch.setattr(
        "builtins.input",
        Mock(side_effect=["owner@example.com", "owner@example.com"]),
    )
    monkeypatch.setattr(
        bootstrap_script.getpass,
        "getpass",
        Mock(side_effect=[password, password]),
    )

    asyncio.run(bootstrap_script.bootstrap_from_prompt(reset=True))

    assert PasswordHasher().verify(owner.password_hash, password)
    assert isinstance(save_session.add.call_args.args[0], PlatformAuditLog)
    assert save_session.add.call_args.args[0].action == "password_reset"
    save_session.execute.assert_awaited_once()
    assert capsys.readouterr().out == "Updated platform owner owner@example.com.\n"


def test_development_environment_requires_allow_dev(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setattr(sys, "argv", ["bootstrap_platform_owner"])

    with pytest.raises(SystemExit) as error:
        bootstrap_script.main()

    assert error.value.code == 2
