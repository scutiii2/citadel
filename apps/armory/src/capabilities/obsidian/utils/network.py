"""Pin each HTTPS connection to a checked DNS answer; never use proxy redirects."""
import http.client
import ipaddress
import socket
import urllib.request

from src.utils.catalog import catalog


@catalog
def checked_addresses(host: str, port: int, *, personal: bool) -> list:
    answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not answers:
        raise OSError("No address")
    for family, _, _, _, address in answers:
        ip = ipaddress.ip_address(address[0].split("%", 1)[0])
        ip = ip.ipv4_mapped if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped else ip
        # Private LAN is deliberate. Loopback/link-local/metadata and non-unicast
        # ranges are never a personal backend destination, including mixed DNS.
        if personal and (ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified
                         or ip.is_reserved or str(ip) in {"100.100.100.200", "168.63.129.16"}):
            raise OSError("Destination is not allowed")
    return answers


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, personal: bool, **kwargs):
        super().__init__(*args, **kwargs)
        self.personal = personal

    def connect(self):
        answers = checked_addresses(self.host, self.port, personal=self.personal)
        last = None
        for family, socktype, proto, _, address in answers:
            sock = socket.socket(family, socktype, proto)
            try:
                sock.settimeout(self.timeout)
                sock.connect(address)
                self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
                return
            except OSError as error:
                sock.close()
                last = error
        raise OSError("Unable to connect to checked destination") from last


class PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, *, context, personal: bool):
        super().__init__(context=context)
        self.personal = personal

    def https_open(self, request):
        def connect(*args, **kwargs):
            return PinnedHTTPSConnection(*args, personal=self.personal, **kwargs)
        return self.do_open(connect, request, context=self._context)
