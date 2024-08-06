from datetime import timedelta

from pathlib import Path

import dotenv
from nostr_sdk import Keys, Client, NostrSigner, Options
from nostr_dvm.utils.dvmconfig import DVMConfig
from nostr_dvm.utils.nostr_utils import check_and_set_private_key

from nut_wallet_utils import create_nut_wallet, get_nut_wallet, NutWallet, create_unspent_proof_event, mint_token, \
    client_connect, announce_nutzap_info_event
import asyncio



async def create_new_or_fetch_nut_wallet(mint_urls, relays, name, description):
    client, dvm_config, keys, = await client_connect(relays)

    nut_wallet = await get_nut_wallet(client, keys)
    if nut_wallet is not None:
        print("Wallet already exists, returnig existing Wallet")
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

    await create_nut_wallet(new_nut_wallet, client, dvm_config)

    print(new_nut_wallet.name + ": " + str(new_nut_wallet.balance) + " " + new_nut_wallet.unit + " Mints: " + str(
        new_nut_wallet.mints) + " Key: " + new_nut_wallet.privkey)

    return new_nut_wallet


async def update_nut_wallet(nut_wallet, mint, additional_amount, relays):
    client, dvm_config, keys, = await client_connect(relays)

    dvm_config = DVMConfig()
    dvm_config.PRIVATE_KEY = keys.secret_key().to_hex()

    nut_wallet.balance = int(nut_wallet.balance) + int(additional_amount)
    if mint not in nut_wallet.mints:
        nut_wallet.mints.append(mint)
    await create_nut_wallet(nut_wallet, client, dvm_config)

    print(nut_wallet.name + ": " + str(nut_wallet.balance) + " " + nut_wallet.unit + " Mints: " + str(
        nut_wallet.mints) + " Key: " + nut_wallet.privkey)

    return nut_wallet


async def mint_cashu(nut_wallet: NutWallet, mint_urls, relays, amount):
    client, dvm_config, keys = await client_connect(relays)
    mint = mint_urls[0]  # TODO consider strategy to pick mint
    proofs = await mint_token(mint, amount)
    print(proofs)
    additional_amount = await create_unspent_proof_event(nut_wallet, proofs, mint, client, dvm_config)
    print("Additional amount " + str(additional_amount))
    await update_nut_wallet(nut_wallet, mint, additional_amount, relays)

if __name__ == '__main__':
    env_path = Path('.env')
    if env_path.is_file():
        print(f'loading environment from {env_path.resolve()}')
        dotenv.load_dotenv(env_path, verbose=True, override=True)
    else:
        raise FileNotFoundError(f'.env file not found at {env_path} ')

    reannounce_mint_info = False
    mint_10_sats = False

    nut_wallet = asyncio.run(
        create_new_or_fetch_nut_wallet(["https://mint.minibits.cash/Bitcoin"], ["wss://relay.primal.net", "wss://nostr.mom"],
                              "Test", "My Nutsack"))
    if reannounce_mint_info:
        asyncio.run(announce_nutzap_info_event(["https://mint.minibits.cash/Bitcoin"], ["wss://relay.primal.net", "wss://nostr.mom"]))
    if mint_10_sats:
        test_mint = asyncio.run(mint_cashu(nut_wallet, ["https://mint.minibits.cash/Bitcoin"], ["wss://relay.primal.net","wss://nostr.mom"], 10))
