import pytest
from algokit_utils import (
    ApplicationClient,
    ApplicationSpecification,
    get_localnet_default_account,
)
from algosdk.v2client.algod import AlgodClient

from smart_contracts.blackjack import contract as blackjack_contract


@pytest.fixture(scope="session")
def blackjack_app_spec(algod_client: AlgodClient) -> ApplicationSpecification:
    return blackjack_contract.app.build(algod_client)


@pytest.fixture(scope="session")
def blackjack_client(
    algod_client: AlgodClient, blackjack_app_spec: ApplicationSpecification
) -> ApplicationClient:
    client = ApplicationClient(
        algod_client,
        app_spec=blackjack_app_spec,
        signer=get_localnet_default_account(algod_client),
    )
    client.create()
    return client


def test_says_hello(blackjack_client: ApplicationClient) -> None:
    result = blackjack_client.call(blackjack_contract.hello, name="World")

    assert result.return_value == "Hello, World"
