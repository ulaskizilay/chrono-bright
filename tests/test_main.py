"""Tests for :mod:`chronobright.__main__`."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from chronobright.__main__ import main


@patch("chronobright.__main__.SingleInstanceLock")
@patch("chronobright.__main__.ChronoBrightApp")
def test_main_starts_app(mock_app_cls: MagicMock, mock_lock_cls: MagicMock) -> None:
    mock_lock_cls.return_value.acquire.return_value = True
    app = mock_app_cls.return_value
    app._is_exiting = True
    main([])
    app.mainloop.assert_called_once()


@patch("chronobright.__main__.SingleInstanceLock")
@patch("chronobright.__main__.ChronoBrightApp", side_effect=RuntimeError("startup failed"))
@patch("chronobright.__main__.sys.exit")
def test_main_exits_with_error_on_exception(
    mock_exit: MagicMock, mock_app_cls: MagicMock, mock_lock_cls: MagicMock
) -> None:
    mock_lock_cls.return_value.acquire.return_value = True
    main([])
    mock_exit.assert_called_once_with(1)


@patch("chronobright.__main__.SingleInstanceLock")
@patch("chronobright.__main__.ChronoBrightApp")
@patch("chronobright.__main__.sys.exit")
def test_main_exits_when_already_running(
    mock_exit: MagicMock, mock_app_cls: MagicMock, mock_lock_cls: MagicMock
) -> None:
    mock_lock_cls.return_value.acquire.return_value = False
    main([])
    mock_exit.assert_called_once_with(2)
    mock_app_cls.assert_not_called()


@patch("chronobright.__main__.SingleInstanceLock")
@patch("chronobright.__main__.ChronoBrightApp")
def test_main_minimized_starts_hidden(
    mock_app_cls: MagicMock, mock_lock_cls: MagicMock
) -> None:
    mock_lock_cls.return_value.acquire.return_value = True
    app = mock_app_cls.return_value
    app._is_exiting = True
    main(["--minimized"])
    app.withdraw.assert_called_once()
    app.mainloop.assert_called_once()
