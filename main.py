import json
from pathlib import Path

import dotenv
from cashu.core.base import Proof
from cashu.wallet.wallet import Wallet
from nostr_sdk import PublicKey, Filter, Kind, Timestamp, HandleNotification, Event, SingleLetterTag, Alphabet
from nostr_dvm.utils.print import bcolors
from secp256k1 import PrivateKey

from nut_wallet_utils import get_nut_wallet, announce_nutzap_info_event, mint_cashu, \
    send_nut_zap, create_new_nut_wallet, client_connect, add_proofs_to_wallet, update_nut_wallet

import asyncio


async def test(relays, mints):
    update_wallet_info = False  # leave this on false except when you manually changed relays/mints/keys
    client, dvm_config, keys, = await client_connect(relays)

    # Test 1 Config: Mint Tokens
    mint_to_wallet = True  # Test function to mint 5 sats on the mint in your list with given index below
    mint_index = 0  # Index of mint in mints list to mint a token
    mint_amount = 5  # Amount to mint

    # Test 2 Config: Send Nutzap
    send_test = True  # Send a Nutzap
    send_zap_amount = 4
    send_zap_message = "From my nutsack"
    send_reveiver = keys.public_key().to_bech32()  # This is ourself, for testing purposes,  some other people to nutzap:  #npub1nxa4tywfz9nqp7z9zp7nr7d4nchhclsf58lcqt5y782rmf2hefjquaa6q8 # dbth  #npub1l2vyh47mk2p0qlsku7hg0vn29faehy9hy34ygaclpn66ukqp3afqutajft # pablof7z
    send_zapped_event = None  # None, or zap an event like this: Nip19Event.from_nostr_uri("nostr:nevent1qqsxq59mhz8s6aj9jzltcmqmmv3eutsfcpkeny2x755vdu5dtq44ldqpz3mhxw309ucnydewxqhrqt338g6rsd3e9upzp75cf0tahv5z7plpdeaws7ex52nmnwgtwfr2g3m37r844evqrr6jqvzqqqqqqyqtxyr6").event_id().to_hex()


    print("PrivateKey: " + keys.secret_key().to_bech32() + " PublicKey: " + keys.public_key().to_bech32())
    # See if we already have a wallet and fetch it
    nut_wallet = await get_nut_wallet(client, keys)

    # If we have a wallet but want to maually update the info..
    if nut_wallet is not None and update_wallet_info:
        await update_nut_wallet(nut_wallet, mints, 0, client, keys)
        await announce_nutzap_info_event(nut_wallet, client, keys)

    # If we don't have a wallet, we create one, fetch it and announce our info
    if nut_wallet is None:
        await create_new_nut_wallet(mints, relays, client, keys, "Test", "My Nutsack")
        nut_wallet = await get_nut_wallet(client, keys)
        if nut_wallet is not None:
            await announce_nutzap_info_event(nut_wallet, client, keys)
        else:
            print("Couldn't fetch wallet, please restart and see if it is there")

    # Test 1: We mint to our own wallet
    if mint_to_wallet:
        await mint_cashu(nut_wallet, mints[mint_index], client, keys, mint_amount)
        nut_wallet = await get_nut_wallet(client, keys)

    # Test 2: We send a nutzap to someone (can be ourselves)
    if send_test:
        zapped_event_id_hex = send_zapped_event
        zapped_user_hex = PublicKey.parse(send_reveiver).to_hex()

        await send_nut_zap(send_zap_amount, send_zap_message, nut_wallet, zapped_event_id_hex, zapped_user_hex, client,
                           keys)
        await get_nut_wallet(client, keys)


async def nostr_client(relays, mints):
    client, dvm_config, keys, = await client_connect(relays)

    from_time = Timestamp.from_secs(Timestamp.now().as_secs() - 60)

    nut_zap_filter = Filter().pubkey(keys.public_key()).kinds([Kind(9321)]).since(from_time).custom_tag(
        SingleLetterTag.lowercase(Alphabet.U),
        mints)

    await client.subscribe([nut_zap_filter], None)

    class NotificationHandler(HandleNotification):
        async def handle(self, relay_url, subscription_id, event: Event):
            #print(f"Received new event from {relay_url}: {event.as_json()}")

            # If we receive a nutzap addressed to us, with our mints, we claim the proofs
            if event.kind().as_u64() == 9321:
                print(bcolors.CYAN + "[Client] " + event.as_json() + bcolors.ENDC)

                nut_wallet = await get_nut_wallet(client, keys)
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

                await add_proofs_to_wallet(nut_wallet, mint_url, proofs, client, keys)
                await get_nut_wallet(client, keys)

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
