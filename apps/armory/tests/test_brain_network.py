import socket

import pytest

from src.capabilities.obsidian.utils.network import checked_addresses


@pytest.mark.parametrize("ip", ["127.0.0.1", "169.254.169.254", "::1", "::ffff:127.0.0.1", "100.100.100.200"])
def test_personal_refuses_backend_and_metadata(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))])
    with pytest.raises(OSError):
        checked_addresses("vault.test", 443, personal=True)


def test_lan_allowed_but_mixed_dns_refused_and_rechecked(monkeypatch):
    answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.50", 443))]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: list(answers))
    assert checked_addresses("vault.test", 443, personal=True) == answers
    answers.append((socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)))
    with pytest.raises(OSError):
        checked_addresses("vault.test", 443, personal=True)
    assert checked_addresses("vault.test", 443, personal=False) == answers
