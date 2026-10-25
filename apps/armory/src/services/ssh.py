"""One SSH client for the whole server, so connection handling, auth fallback, host-key verification and timeouts are identical everywhere.
Host keys are verified against ``settings.ssh_known_hosts``; unknown ones are rejected. Set ``SSH_HOST_KEY_POLICY=auto`` for trust-on-first-use."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

import paramiko

from src.config import settings


def _new_client(
    *,
    known_hosts: Path | str | None = None,
    host_key_policy: str | None = None,
) -> paramiko.SSHClient:
    """A paramiko client with host-key verification already set up; every connect path goes through here."""
    policy_name = (host_key_policy or settings.ssh_host_key_policy).strip().lower()
    if policy_name not in {"reject", "auto"}:
        raise ValueError(
            f"Unknown SSH_HOST_KEY_POLICY {policy_name!r} - expected 'reject' or 'auto'."
        )

    path = Path(known_hosts) if known_hosts is not None else settings.ssh_known_hosts
    client = paramiko.SSHClient()

    if policy_name == "auto" and not path.exists():
        # Create it so paramiko can persist accepted keys; load_host_keys() raises if the file is missing.
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    if path.exists():
        client.load_host_keys(str(path))

    client.set_missing_host_key_policy(
        paramiko.AutoAddPolicy() if policy_name == "auto" else paramiko.RejectPolicy()
    )
    return client


@dataclass
class SSHCommandResult:
    stdout: str
    stderr: str
    exit_status: int

    @property
    def ok(self) -> bool:
        return self.exit_status == 0


class SSHClient:
    """Context-manager SSH connection with key-then-password auth fallback.
    Usage: ``with SSHClient(host, user, key=key_path, password=password) as ssh: ssh.run("...")``."""

    def __init__(
        self,
        host: str,
        user: str,
        *,
        key: str | None = None,
        password: str | None = None,
        port: int = 22,
        connect_timeout: int = 10,
        command_timeout: int = 30,
        known_hosts: Path | str | None = None,
        host_key_policy: str | None = None,
    ) -> None:
        self.host = host
        self.user = user
        self.key = key
        self.password = password
        self.port = port
        self.connect_timeout = connect_timeout
        self.command_timeout = command_timeout
        self.known_hosts = known_hosts
        self.host_key_policy = host_key_policy
        self._client: paramiko.SSHClient | None = None

    def __enter__(self) -> "SSHClient":
        self._client = _new_client(
            known_hosts=self.known_hosts, host_key_policy=self.host_key_policy
        )
        self._connect()
        return self

    def _connect(self) -> None:
        assert self._client is not None
        last_error: Exception | None = None

        if self.key:
            try:
                self._client.connect(
                    hostname=self.host,
                    port=self.port,
                    username=self.user,
                    key_filename=self.key,
                    timeout=self.connect_timeout,
                    look_for_keys=False,
                    allow_agent=False,
                )
                return
            except Exception as error:  # noqa: BLE001 - fall through to password
                last_error = error

        if self.password:
            try:
                self._client.connect(
                    hostname=self.host,
                    port=self.port,
                    username=self.user,
                    password=self.password,
                    timeout=self.connect_timeout,
                    look_for_keys=False,
                    allow_agent=False,
                )
                return
            except Exception as error:  # noqa: BLE001
                last_error = error

        # Not just "auth failed": with host-key verification on, the likely first-run failure is an unknown host key,
        # and calling it an auth problem sends you checking passwords for nothing.
        hint = ""
        if isinstance(last_error, paramiko.SSHException) and "known_hosts" in str(last_error):
            hint = (
                f" The host key for {self.host} is not in "
                f"{self.known_hosts or settings.ssh_known_hosts}. Add it "
                f"(ssh-keyscan, or connect once with the ssh client), or set "
                f"SSH_HOST_KEY_POLICY=auto to trust on first use."
            )
        raise ConnectionError(
            f"SSH connection to {self.user}@{self.host} failed: {last_error}.{hint}"
        )

    def run(self, command: str) -> SSHCommandResult:
        assert self._client is not None, "SSHClient must be used as a context manager"
        _stdin, stdout, stderr = self._client.exec_command(command, timeout=self.command_timeout)
        out = stdout.read().decode(errors="replace")
        err = stderr.read().decode(errors="replace")
        code = stdout.channel.recv_exit_status()
        return SSHCommandResult(stdout=out, stderr=err, exit_status=code)

    def run_login_shell(self, command: str, shell: str = "bash") -> SSHCommandResult:
        """Run a command through an actual login shell, since a bare exec_command() sources no profile and may not find binaries on PATH.
        ``shell`` picks the wrapper ("bash" default, "csh" for .cshrc accounts). ``command`` is shell-quoted because tool arguments originate from an LLM and may come from attacker-controlled text."""
        quoted = shlex.quote(command)
        if shell == "csh":
            wrapped = f"/bin/csh -c {quoted}"
        else:
            wrapped = f"/bin/bash -lc {quoted}"
        return self.run(wrapped)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._client is not None:
            self._client.close()


def run_command(
    host: str,
    user: str,
    *,
    key: str | None = None,
    password: str | None = None,
    command: str,
    timeout: int = 30,
) -> tuple[bool, str, str]:
    """Bare exec_command (no login shell), returning (connected, stdout, stderr).
    "connected" means the connection and execution completed, not that the command exited 0; use ``SSHClient`` for the exit status or ``run_login_shell()`` if the profile is needed for PATH."""
    try:
        with SSHClient(host, user, key=key, password=password, command_timeout=timeout) as ssh:
            result = ssh.run(command)
            return True, result.stdout, result.stderr
    except ConnectionError as error:
        return False, "", str(error)


def sftp_upload_dir(host: str, user: str, password: str, local_dir: str, remote_dir: str) -> int:
    """Recursively upload local_dir's contents into remote_dir over SFTP with password auth; returns the file count.
    Opens its own connection (``SSHClient`` has no SFTP channel), so files must already be staged on this machine."""
    import os

    client = _new_client()
    client.connect(hostname=host, username=user, password=password, timeout=15, look_for_keys=False, allow_agent=False)
    sftp = client.open_sftp()
    try:
        def _mkdir_p(path: str) -> None:
            path = path.rstrip("/") or "/"
            try:
                sftp.stat(path)
            except FileNotFoundError:
                parent = path.rsplit("/", 1)[0] or "/"
                if parent != path:
                    _mkdir_p(parent)
                sftp.mkdir(path)

        uploaded = 0
        for root, _dirs, files in os.walk(local_dir):
            rel = os.path.relpath(root, local_dir).replace("\\", "/")
            remote_root = remote_dir if rel == "." else f"{remote_dir}/{rel}"
            _mkdir_p(remote_root)
            for fname in files:
                local_path = os.path.join(root, fname)
                remote_path = f"{remote_root}/{fname}"
                sftp.put(local_path, remote_path)
                uploaded += 1
        return uploaded
    finally:
        sftp.close()
        client.close()


def sftp_write_file(host: str, user: str, key: str | None, password: str | None, remote_path: str, content: str) -> None:
    """Write a single small text file to the remote host over SFTP, e.g. to stage a script before ``SSHClient.run()``.
    Unlike ``sftp_upload_dir``, it writes one string to one remote path."""
    client = _new_client()
    try:
        if key:
            client.connect(hostname=host, username=user, key_filename=key, timeout=10, look_for_keys=False, allow_agent=False)
        else:
            client.connect(hostname=host, username=user, password=password, timeout=10, look_for_keys=False, allow_agent=False)
        sftp = client.open_sftp()
        with sftp.file(remote_path, "w") as f:
            f.write(content)
        sftp.close()
    finally:
        client.close()
