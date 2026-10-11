import sys
from unittest.mock import Mock

import pytest

import fake_driver


def test_fake_driver_reads_token_from_environment_without_printing(
    monkeypatch, capsys
):
    token = "private-driver-token"
    simulator = Mock()
    monkeypatch.setenv("FAKE_DRIVER_TOKEN", token)
    monkeypatch.setattr(fake_driver, "DriverSimulator", Mock(return_value=simulator))
    monkeypatch.setattr(sys, "argv", ["fake_driver"])

    fake_driver.main()

    fake_driver.DriverSimulator.assert_called_once_with(token, fake_driver.DEFAULT_URL)
    simulator.run.assert_called_once_with()
    captured = capsys.readouterr()
    assert token not in captured.out
    assert token not in captured.err


def test_fake_driver_rejects_command_line_token_without_echoing_it(
    monkeypatch, capsys
):
    token = "private-driver-token"
    monkeypatch.setattr(sys, "argv", ["fake_driver", "--token", token])

    with pytest.raises(SystemExit) as error:
        fake_driver.main()

    assert error.value.code == 2
    captured = capsys.readouterr()
    assert token not in captured.out
    assert token not in captured.err
    assert "Do not pass driver tokens on the command line" in captured.err
