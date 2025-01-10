from typing import List

from lonelypsc.config.file_config import get_auth_config_from_file
from lonelypsc.config.http_config import HttpPubSubConfig, make_http_pub_sub_config
from lonelypsc.config.ws_config import (
    WebsocketPubSubConfig,
    make_websocket_pub_sub_config,
)
from lonelypsp.auth.config import AuthConfig, AuthConfigFromParts


class ConfigGen:
    """Generates the configuration settings for the client to connect to a
    particular cluster
    """

    def __init__(self, ips: List[str], auth_file_path: str) -> None:
        self.ips = ips
        """ips and ports where the instances can be reached"""

        self.auth_file_path = auth_file_path
        """subscriber-secrets.json"""

    def auth(self) -> AuthConfig:
        to_subscriber, to_broadcaster = get_auth_config_from_file(self.auth_file_path)
        return AuthConfigFromParts(
            to_subscriber=to_subscriber, to_broadcaster=to_broadcaster
        )

    def http(self, port: int) -> HttpPubSubConfig:
        """Generates the configuration to connect over http"""
        return make_http_pub_sub_config(
            bind={"type": "uvicorn", "host": "0.0.0.0", "port": port},
            host=f"http://127.0.0.1:{port}",
            broadcasters=[{"host": f"http://{ip}"} for ip in self.ips],
            outgoing_retries_per_broadcaster=2,
            message_body_spool_size=1024 * 1024 * 10,
            outgoing_http_timeout_total=30,
            outgoing_http_timeout_connect=None,
            outgoing_http_timeout_sock_read=None,
            outgoing_http_timeout_sock_connect=5,
            outgoing_retry_ambiguous=True,
            auth=self.auth(),
        )

    def websocket(self) -> WebsocketPubSubConfig:
        """Generates the configuration to connect over websocket"""
        return make_websocket_pub_sub_config(
            broadcasters=[
                {"host": "ws://127.0.0.1:3003"},
            ],
            outgoing_initial_connect_retries=2,
            outgoing_min_reconnect_interval=1,
            max_websocket_message_size=1024 * 128,
            websocket_open_timeout=5,
            websocket_close_timeout=5,
            websocket_heartbeat_interval=10,
            websocket_minimal_headers=True,
            max_sent_notifications=None,
            max_unsent_notifications=None,
            max_expected_acks=None,
            max_received=None,
            max_unsent_acks=None,
            allow_compression=True,
            compression_dictionary_by_id=dict(),
            initial_compression_dict_id=None,
            allow_training_compression=True,
            decompression_max_window_size=0,
            auth=self.auth(),
        )
