import asyncio
from datetime import timedelta

from pathlib import Path

import dotenv
from nostr_sdk import Keys, Client, NostrSigner, Options
from nostr_dvm.utils.dvmconfig import DVMConfig
from nostr_dvm.utils.nostr_utils import check_and_set_private_key

from nut_wallet_utils import create_nut_wallet, get_nut_wallet, NutWallet


async def test():
    dvmconfig = DVMConfig()
    relay_list = dvmconfig.RELAY_LIST
    keys = Keys.parse(check_and_set_private_key("RTEST_ACCOUNT_PK"))
    pk = keys.secret_key().to_hex()
    dvmconfig.PRIVATE_KEY = pk
    wait_for_send = False
    skip_disconnected_relays = True
    opts = (Options().wait_for_send(wait_for_send).send_timeout(timedelta(seconds=5))
            .skip_disconnected_relays(skip_disconnected_relays))

    signer = NostrSigner.keys(keys)
    client = Client.with_opts(signer, opts)

    for relay in relay_list:
        await client.add_relay(relay)
    await client.connect()

    nut_wallet = await get_nut_wallet(client, keys)

    #nut_wallet.name = None

    # Create Nostr Wallet if it doesn't exist
    if nut_wallet is None:
        dvm_config = DVMConfig()
        dvm_config.PRIVATE_KEY = keys.secret_key().to_hex()
        dvm_config.NIP89.NAME = "Nutzap"

        new_nut_wallet = NutWallet()
        new_nut_wallet.privkey = "" # TODO how to get
        new_nut_wallet.balance = 0
        new_nut_wallet.unit = "sat"

        new_nut_wallet.name = "Test"
        new_nut_wallet.description = "My Test Wallet"
        new_nut_wallet.mints = ["https://mint.minibits.cash/Bitcoin"]
        new_nut_wallet.relays = dvm_config.RELAY_LIST

        await create_nut_wallet(new_nut_wallet, client, dvm_config)
        nut_wallet = await get_nut_wallet(client, keys)

    print(nut_wallet.name + ": " + str(nut_wallet.balance) + " " + nut_wallet.unit + " Mints: " + str(
        nut_wallet.mints))


if __name__ == '__main__':
    env_path = Path('.env')
    if env_path.is_file():
        print(f'loading environment from {env_path.resolve()}')
        dotenv.load_dotenv(env_path, verbose=True, override=True)
    else:
        raise FileNotFoundError(f'.env file not found at {env_path} ')

    asyncio.run(test())
