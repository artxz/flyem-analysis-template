"""Lazy connection to neuPrint.

Importing this module never touches the network or needs a token. The first
call to `get_client()` or `connect()` opens the connection.

Server and dataset come from, in order: the arguments, then
`NEUPRINT_SERVER_URL` / `NEUPRINT_DATASET_NAME` (for example from `.env`), then
the default dataset in `config.DATASETS`. The token always comes from
`NEUPRINT_APPLICATION_CREDENTIALS`.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from . import config

if TYPE_CHECKING:
    from neuprint import Client

__all__ = ["NeuprintConnectionError", "connect", "get_client"]

_TOKEN_VAR = "NEUPRINT_APPLICATION_CREDENTIALS"
_HOW_TO_FIX = (
    "Copy .env.example to .env (in the project folder, or in your current folder "
    f"for an installed copy), set {_TOKEN_VAR} to the token from your neuPrint "
    "account page (https://neuprint.janelia.org/account), and restart the kernel."
)

_clients: dict[tuple[str, str], Client] = {}


class NeuprintConnectionError(RuntimeError):
    """Raised when no neuPrint connection can be made, with a hint on how to fix it."""


def _resolve(server: str | None, dataset: str | None) -> tuple[str, str]:
    """Return the `(server, dataset name)` to connect to.

    Args:
        server: Server URL, or `None` for the default.
        dataset: neuPrint dataset name (`male-cns:v1.0`) or registry tag
            (`malecns_v1.0`), or `None` for the default.

    Returns:
        Server URL and neuPrint dataset name.
    """
    if dataset in config.DATASETS:
        ds = config.DATASETS[dataset]
        return server or ds.server, ds.name
    default = config.DATASETS[config.DEFAULT_DATASET]
    if dataset is None:
        dataset = os.environ.get("NEUPRINT_DATASET_NAME") or default.name
    if server is None:
        # A known dataset name picks its own server, unless the env says otherwise.
        known = {d.name: d.server for d in config.DATASETS.values()}
        server = os.environ.get("NEUPRINT_SERVER_URL") or known.get(
            dataset, default.server
        )
    return server, dataset


def connect(
    verbose: bool = False,
    server: str | None = None,
    dataset: str | None = None,
) -> Client:
    """Open a neuPrint connection and make it the default client.

    neuprint-python and navis functions called without `client=` then use it.
    Repeated calls with the same server and dataset reuse the open connection.

    Args:
        verbose: Print the server, dataset and neuprint-python version.
        server: neuPrint server URL. Defaults to `NEUPRINT_SERVER_URL`, then
            the server of the dataset in `config.DATASETS`.
        dataset: neuPrint dataset name (`male-cns:v1.0`) or registry tag
            (`malecns_v1.0`). Defaults to `NEUPRINT_DATASET_NAME`, then
            `config.DEFAULT_DATASET`.

    Returns:
        The connected `neuprint.Client`.

    Raises:
        NeuprintConnectionError: No token is set, or the server refused the
            connection.
    """
    import neuprint

    server, dataset = _resolve(server, dataset)
    key = (server, dataset)
    client = _clients.get(key)
    if client is None:
        if not os.environ.get(_TOKEN_VAR):
            raise NeuprintConnectionError(f"No neuPrint token found. {_HOW_TO_FIX}")
        try:
            client = neuprint.Client(server, dataset=dataset)
        except Exception as err:  # neuprint raises RuntimeError and HTTPError
            raise NeuprintConnectionError(
                f"Could not connect to {server} [{dataset}]: {err}\n"
                f"If the token is wrong or expired: {_HOW_TO_FIX}"
            ) from err
        _clients[key] = client
    neuprint.set_default_client(client)
    if verbose:
        print(f"Connected to {server} [{dataset}].")
        print(f"Client: neuprint-python v{neuprint.__version__}")
    return client


def get_client(dataset: str | None = None) -> Client:
    """Return a neuPrint client, connecting on first use.

    With no `dataset`, this is the client from the last `connect()` call, or
    the default client set some other way (for example a `neuprint.Client`
    created by hand), or a new connection to the default dataset.

    Args:
        dataset: neuPrint dataset name or registry tag; `None` for the default.

    Returns:
        A connected `neuprint.Client`.

    Raises:
        NeuprintConnectionError: No connection could be made (see `connect`).
    """
    if dataset is None:
        import neuprint

        try:
            return neuprint.default_client()
        except Exception:  # neuprint raises RuntimeError when none is set
            pass
    return connect(dataset=dataset)
