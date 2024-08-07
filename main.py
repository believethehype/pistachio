import json
import os
from pathlib import Path

import dotenv
from cashu.core.base import Proof
from cashu.wallet.wallet import Wallet
from nostr_sdk import PublicKey, Filter, Kind, Timestamp, HandleNotification, Event, SingleLetterTag, Alphabet
from nostr_dvm.utils.print import bcolors
from secp256k1 import PrivateKey

from nut_wallet_utils import get_nut_wallet, announce_nutzap_info_event, mint_cashu, \
    send_nut_zap, create_new_nut_wallet, update_nut_wallet, client_connect, get_mint, create_unspent_proof_event, \
    update_mint_proof_event, add_proofs_to_wallet

import asyncio


async def test(relays, mints):
    # On first run dont mint or send, that kinda doesnt save the event rn
    mint_5_sats = False
    send_test = True

    nut_wallet = await get_nut_wallet(relays)

    # await update_nut_wallet(nut_wallet, mints, 0, relays)
    await announce_nutzap_info_event(nut_wallet)

    if nut_wallet is None:
        nut_wallet = await create_new_nut_wallet(mints, relays, "Test", "My Nutsack")
        await announce_nutzap_info_event(nut_wallet)
        nut_wallet = await get_nut_wallet(relays)

    if mint_5_sats:
        await mint_cashu(nut_wallet, mints[0], relays, 5)
        nut_wallet = await get_nut_wallet(relays)

    if send_test:
        zapped_event_id_hex = ""  # Nip19Event.from_nostr_uri(
        # "nostr:nevent1qqsxq59mhz8s6aj9jzltcmqmmv3eutsfcpkeny2x755vdu5dtq44ldqpz3mhxw309ucnydewxqhrqt338g6rsd3e9upzp75cf0tahv5z7plpdeaws7ex52nmnwgtwfr2g3m37r844evqrr6jqvzqqqqqqyqtxyr6").event_id().to_hex()
        # zapped_user_hex = PublicKey.parse("npub1nxa4tywfz9nqp7z9zp7nr7d4nchhclsf58lcqt5y782rmf2hefjquaa6q8").to_hex()
        # zapped_user_hex = PublicKey.parse("npub1l2vyh47mk2p0qlsku7hg0vn29faehy9hy34ygaclpn66ukqp3afqutajft").to_hex()
        zapped_user_hex = PublicKey.parse("npub18ghjrqkmppc9jv3gv4gw6mjgqga7eygq2ewjzyntn5htz6x6sslqw39l4w").to_hex()

        await send_nut_zap(4, "From my nutsack", nut_wallet, zapped_event_id_hex, zapped_user_hex, relays)
        await get_nut_wallet(relays)


async def nostr_client(relays, mints):
    client, dvm_config, keys, = await client_connect(relays)

    from_time = Timestamp.from_secs(Timestamp.now().as_secs() - 60)

    nut_zap_filter = Filter().pubkey(keys.public_key()).kinds([Kind(9321)]).since(from_time).custom_tag(
        SingleLetterTag.lowercase(Alphabet.U),
        mints)

    await client.subscribe([nut_zap_filter], None)

    class NotificationHandler(HandleNotification):
        async def handle(self, relay_url, subscription_id, event: Event):
            print(f"Received new event from {relay_url}: {event.as_json()}")
            if event.kind().as_u64() == 9321:
                print(bcolors.CYAN + "[Client] " + event.as_json() + bcolors.ENDC)

                nut_wallet = await get_nut_wallet(relays)
                proofs = []
                mint_url = ""
                amount = 0
                unit = "sat"
                zapped_user = ""
                zapped_event = ""
                for tag in event.tags():
                    if tag.as_vec()[0] == "proof":
                        proof_json = json.loads(tag.as_vec()[1])
                        proof = Proof().from_dict(proof_json)
                        proofs.append(proof)
                    elif tag.as_vec()[0] == "u":
                        mint_url = tag.as_vec()[1]
                    elif tag.as_vec()[0] == "amount":
                        amount = int(tag.as_vec()[1])
                    elif tag.as_vec()[0] == "unit":
                        unit = tag.as_vec()[1]
                    elif tag.as_vec()[0] == "p":
                        zapped_user = tag.as_vec()[1]
                    elif tag.as_vec()[0] == "e":
                        zapped_event = tag.as_vec()[1]

                cashu_wallet = await Wallet.with_db(
                    url=mint_url,
                    db="db/Receiver",
                    name="receiver",
                )
                cashu_wallet.private_key = PrivateKey(bytes.fromhex(nut_wallet.privkey), raw=True)
                await cashu_wallet.load_mint()

                proofs, _ = await cashu_wallet.redeem(proofs)
                print(proofs)

                await add_proofs_to_wallet(nut_wallet, mint_url, proofs, relays)

        async def handle_msg(self, relay_url, msg):
            return

    await client.handle_notifications(NotificationHandler())
    while True:
        await asyncio.sleep(2.0)


if __name__ == '__main__':
    env_path = Path('.env')
    if env_path.is_file():
        print(f'loading environment from {env_path.resolve()}')
        dotenv.load_dotenv(env_path, verbose=True, override=True)
    else:
        raise FileNotFoundError(f'.env file not found at {env_path} ')

    relays = ["wss://relay.primal.net", "wss://nostr.oxtr.dev"]
    mints = ["https://mint.minibits.cash/Bitcoin", "https://mint.gwoq.com"]
    asyncio.run(test(relays, mints))
    asyncio.run(nostr_client(relays, mints))
