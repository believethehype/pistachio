import asyncio
from datetime import timedelta

from pathlib import Path

import dotenv
from cashu.core.base import TokenV3
from nostr_sdk import Keys, Client, NostrSigner, Options
from nostr_dvm.utils.dvmconfig import DVMConfig
from nostr_dvm.utils.nostr_utils import check_and_set_private_key

from nut_wallet_utils import create_nut_wallet, get_nut_wallet, NutWallet
import asyncio
from cashu.nostr.key import PublicKey, PrivateKey
from cashu_utils import test_info, cashu_wallet, receive_cashu_test, get_cashu_balance


async def make_or_get_nut_wallet(mint_url):
    wallet = await cashu_wallet(mint_url)
    await wallet.load_mint()
    await wallet.load_proofs()

    print(wallet.available_balance)

    #await get_cashu_balance(mint_url)
    #print(PrivateKey(wallet.private_key.private_key).hex())

    dvmconfig = DVMConfig()
    relay_list = ["wss://relay.primal.net",
                  "wss://nostr.mom", "wss://nostr.oxtr.dev", "wss://relay.nostr.bg",
                  "wss://relay.nostr.net"
                  ]
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

    # Create or update Wallet
    dvm_config = DVMConfig()
    dvm_config.PRIVATE_KEY = keys.secret_key().to_hex()
    dvm_config.NIP89.NAME = "Nutzap"

    new_nut_wallet = NutWallet()
    new_nut_wallet.privkey = PrivateKey(wallet.private_key.private_key).hex()
    new_nut_wallet.balance = wallet.available_balance
    new_nut_wallet.unit = "sat"

    new_nut_wallet.name = "Test"
    new_nut_wallet.description = "My Test Wallet"
    new_nut_wallet.mints = [mint_url]
    new_nut_wallet.relays = dvm_config.RELAY_LIST

    await create_nut_wallet(new_nut_wallet, client, dvm_config)
    nut_wallet = await get_nut_wallet(client, keys)

    print(nut_wallet.name + ": " + str(nut_wallet.balance) + " " + nut_wallet.unit + " Mints: " + str(
        nut_wallet.mints)+ " Key: " + nut_wallet.privkey)


async def test_receive(token_str):
    token = TokenV3.deserialize(token_str)
    await receive_cashu_test(token_str)
    await get_cashu_balance(token.token[0].mint)


if __name__ == '__main__':
    env_path = Path('.env')
    if env_path.is_file():
        print(f'loading environment from {env_path.resolve()}')
        dotenv.load_dotenv(env_path, verbose=True, override=True)
    else:
        raise FileNotFoundError(f'.env file not found at {env_path} ')

    asyncio.run(make_or_get_nut_wallet("https://mint.minibits.cash/Bitcoin"))
    #asyncio.run(test_receive("cashuAeyJ0b2tlbiI6W3sibWludCI6Imh0dHBzOi8vbWludC5taW5pYml0cy5jYXNoL0JpdGNvaW4iLCJwcm9vZnMiOlt7ImlkIjoiMDA1MDA1NTBmMDQ5NDE0NiIsImFtb3VudCI6MSwic2VjcmV0IjoiYnFkWUI3ODFkam5jWVkzWmVIcXZweGF4aGlsOWVGTVZPTlBYKzZjUUIwcz0iLCJDIjoiMDI4YmY3YTM3YWQ4ZjFmMzg5OGY5MGFiZGRiN2ZhNzdhYTZlOTEzNGQ4YmNkZmNmN2U2NTFkNzU4M2RjODRlZjRmIn0seyJpZCI6IjAwNTAwNTUwZjA0OTQxNDYiLCJhbW91bnQiOjQsInNlY3JldCI6Im9COHZrRjJvTjBiRDNEanZIM1J2L0diRm1OaVVHMmwwd3RLdjRMNVQ1cm89IiwiQyI6IjAyYThkZmM0NGNjZTE5YTVlNzlmNjQ1ZmY3OGYwNTc2YmEzYTkxNmI5OWVkOGIxN2IwYmFjNDRmZDcyMGRmMGYwMyJ9XX1dLCJtZW1vIjoiU2VudCB2aWEgZU51dHMuIn0"))
