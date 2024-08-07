from pathlib import Path

import dotenv
from nostr_sdk import PublicKey, Nip19Event
from nut_wallet_utils import get_nut_wallet, announce_nutzap_info_event, mint_cashu, \
    send_nut_zap, create_new_nut_wallet
import asyncio


async def test():
    relays = ["wss://relay.primal.net", "wss://nostr.oxtr.dev"]
    mints = ["https://mint.minibits.cash/Bitcoin"]

    # On first run dont mint or send, that kinda doesnt save the event rn
    mint_5_sats = False
    send_test = True

    nut_wallet = await get_nut_wallet(relays)

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
        zapped_user_hex = PublicKey.parse("npub1nxa4tywfz9nqp7z9zp7nr7d4nchhclsf58lcqt5y782rmf2hefjquaa6q8").to_hex()
        #zapped_user_hex = PublicKey.parse("npub1l2vyh47mk2p0qlsku7hg0vn29faehy9hy34ygaclpn66ukqp3afqutajft").to_hex()
        await send_nut_zap(4, "From my nutsack", nut_wallet, zapped_event_id_hex, zapped_user_hex, relays)
        await get_nut_wallet(relays)

if __name__ == '__main__':
    env_path = Path('.env')
    if env_path.is_file():
        print(f'loading environment from {env_path.resolve()}')
        dotenv.load_dotenv(env_path, verbose=True, override=True)
    else:
        raise FileNotFoundError(f'.env file not found at {env_path} ')

    asyncio.run(test())
