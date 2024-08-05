import asyncio
from datetime import timedelta

from pathlib import Path

import dotenv
from cashu.core.base import TokenV3
from nostr_sdk import Keys, Client, NostrSigner, Options
from nostr_dvm.utils.dvmconfig import DVMConfig
from nostr_dvm.utils.nostr_utils import check_and_set_private_key

from nut_wallet_utils import create_nut_wallet, get_nut_wallet, NutWallet, create_unspent_proof_event
import asyncio
from cashu.nostr.key import PublicKey, PrivateKey
from cashu_utils import test_info, cashu_wallet, receive_cashu_test, get_cashu_balance, mint_token


async def client_connect(relay_list):
    dvmconfig = DVMConfig()

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
    return client, keys


async def create_new_nut_wallet(mint_urls, relays, name, description):
    client, keys = await client_connect(relays)

    nut_wallet = await get_nut_wallet(client, keys)
    if nut_wallet is not None:
        print("Wallet already exists, not creating new one")
        return nut_wallet

    dvm_config = DVMConfig()
    dvm_config.PRIVATE_KEY = keys.secret_key().to_hex()

    new_nut_wallet = NutWallet()
    new_nut_wallet.privkey = Keys.generate().secret_key().to_hex()  # PrivateKey(wallet.private_key.private_key).hex()
    new_nut_wallet.balance = 0
    new_nut_wallet.unit = "sat"

    new_nut_wallet.name = name
    new_nut_wallet.description = description
    new_nut_wallet.mints = mint_urls
    new_nut_wallet.relays = dvm_config.RELAY_LIST

    nut_wallet = await create_nut_wallet(new_nut_wallet, client, dvm_config)

    print(nut_wallet.name + ": " + str(nut_wallet.balance) + " " + nut_wallet.unit + " Mints: " + str(
        nut_wallet.mints) + " Key: " + nut_wallet.privkey)

    return new_nut_wallet

async def mint_cashu(mint_urls, amount):

    mint = mint_urls[0] #TODO consider strategy to pick mint
    await mint_token(mint, amount)




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

    nut_wallet = asyncio.run(create_new_nut_wallet(["https://mint.minibits.cash/Bitcoin"],["wss://relay.primal.net","wss://nostr.mom"],  "Test", "My Nutsack"))

    test_mint = asyncio.run(mint_cashu(["https://mint.minibits.cash/Bitcoin"], 10))


    # asyncio.run(test_receive("cashuAeyJ0b2tlbiI6W3sibWludCI6Imh0dHBzOi8vbWludC5taW5pYml0cy5jYXNoL0JpdGNvaW4iLCJwcm9vZnMiOlt7ImlkIjoiMDA1MDA1NTBmMDQ5NDE0NiIsImFtb3VudCI6MSwic2VjcmV0IjoiYnFkWUI3ODFkam5jWVkzWmVIcXZweGF4aGlsOWVGTVZPTlBYKzZjUUIwcz0iLCJDIjoiMDI4YmY3YTM3YWQ4ZjFmMzg5OGY5MGFiZGRiN2ZhNzdhYTZlOTEzNGQ4YmNkZmNmN2U2NTFkNzU4M2RjODRlZjRmIn0seyJpZCI6IjAwNTAwNTUwZjA0OTQxNDYiLCJhbW91bnQiOjQsInNlY3JldCI6Im9COHZrRjJvTjBiRDNEanZIM1J2L0diRm1OaVVHMmwwd3RLdjRMNVQ1cm89IiwiQyI6IjAyYThkZmM0NGNjZTE5YTVlNzlmNjQ1ZmY3OGYwNTc2YmEzYTkxNmI5OWVkOGIxN2IwYmFjNDRmZDcyMGRmMGYwMyJ9XX1dLCJtZW1vIjoiU2VudCB2aWEgZU51dHMuIn0"))
