from datetime import timedelta
from hashlib import sha256

from pathlib import Path

import dotenv
from nostr_sdk import Keys, PublicKey, Nip19Event, Kind
from nostr_dvm.utils.dvmconfig import DVMConfig

from nut_wallet_utils import create_nut_wallet, get_nut_wallet, NutWallet, create_unspent_proof_event, mint_token, \
    client_connect, announce_nutzap_info_event, send_nut_zap, get_mint
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
    key_str = str(new_nut_wallet.name + new_nut_wallet.description)
    new_nut_wallet.d = sha256(key_str.encode('utf-8')).hexdigest()[:16]
    new_nut_wallet.a = str(
        Kind(7375).as_u64()) + ":" + keys.public_key().to_hex() + ":" + new_nut_wallet.d  # TODO maybe this is wrong
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


async def mint_cashu(nut_wallet: NutWallet, mint_url, relays, amount):
    client, dvm_config, keys = await client_connect(relays)

    # Mint the Token at the selected mint
    proofs = await mint_token(mint_url, amount)
    print(proofs)
    additional_amount = 0

    mint = get_mint(nut_wallet, mint_url)
    # store the new proofs in proofs_temp
    proofs_temp = []
    for proof in proofs:
        additional_amount += proof.amount
        proofs_temp.append(proof)

    # check for other proofs from same mint, add them to the list of proofs
    for nut_proof in mint.proofs:
        proofs_temp.append(nut_proof)
        proofs.append(nut_proof)

    print("additional amount: " + str(additional_amount))
    mint.previous_event_id = await create_unspent_proof_event(nut_wallet, proofs_temp, mint_url, client, dvm_config)

    #index = [index for index in range(len(nut_wallet.nutmints)) if nut_wallet.nutmints[index] == mint_url][0]
    #nut_wallet.nutmints[index] = mint

    return await update_nut_wallet(nut_wallet, mint_url, additional_amount, relays)


if __name__ == '__main__':
    env_path = Path('.env')
    if env_path.is_file():
        print(f'loading environment from {env_path.resolve()}')
        dotenv.load_dotenv(env_path, verbose=True, override=True)
    else:
        raise FileNotFoundError(f'.env file not found at {env_path} ')

    reannounce_mint_info = True
    mint_10_sats = False
    send_test = False

    relays = ["wss://relay.primal.net", "wss://nostr.mom"]
    mints = ["https://mint.minibits.cash/Bitcoin"]

    nut_wallet = asyncio.run(
        create_new_or_fetch_nut_wallet(mints, relays, "Test", "My Nutsack"))
    if reannounce_mint_info:
        asyncio.run(announce_nutzap_info_event(mints, relays, nut_wallet))
    if mint_10_sats:
        nut_wallet = asyncio.run(mint_cashu(nut_wallet, mints[0], relays, 10))

    if send_test:
        zapped_event_id_hex = Nip19Event.from_nostr_uri(
            "nostr:nevent1qqsxq59mhz8s6aj9jzltcmqmmv3eutsfcpkeny2x755vdu5dtq44ldqpz3mhxw309ucnydewxqhrqt338g6rsd3e9upzp75cf0tahv5z7plpdeaws7ex52nmnwgtwfr2g3m37r844evqrr6jqvzqqqqqqyqtxyr6").event_id().to_hex()
        zapped_user_hex = PublicKey.parse("npub1l2vyh47mk2p0qlsku7hg0vn29faehy9hy34ygaclpn66ukqp3afqutajft").to_hex()
        asyncio.run(send_nut_zap(5, "From my nutsack", nut_wallet, zapped_event_id_hex, zapped_user_hex, relays))
