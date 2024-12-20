import asyncio
from datetime import timedelta
from pathlib import Path

import dotenv
from nostr_dvm.utils.nostr_utils import check_and_set_private_key
from nostr_sdk import HandleNotification, Event, Filter, SingleLetterTag, Alphabet, Kind, Timestamp, LogLevel, \
    init_logger, EventSource, Keys

from nut_wallet_utils import NutZapWallet
from nostr_dvm.utils.print_utils import bcolors

use_logger = True
log_level = LogLevel.INFO
if use_logger:
    init_logger(log_level)

async def nostr_client(relays, mints, show_history):
    nutzap_wallet_client = NutZapWallet()
    keys = Keys.parse(check_and_set_private_key("receiver"))
    client = await nutzap_wallet_client.client_connect(relays, keys)

    # per default, check events within the last 60 seconds
    from_time = Timestamp.from_secs(Timestamp.now().as_secs() - 60)

    # but eventually, we check all events since the last time a transaction was made
    # therefore we fetch the transaction history (Maybe we limit this to 1 in the future)
    transaction_history_filter = Filter().author(keys.public_key()).kinds([Kind(7376)])  # .limit(1)

    transactions = await client.fetch_events([transaction_history_filter], timedelta(seconds=10))

    # If we find transactions, we look for all events since right after the last one
    print("\n" + bcolors.CYAN + "Transaction History:" + bcolors.ENDC)
    if len(transactions.to_vec()) > 0:
        from_time = Timestamp.from_secs(transactions.to_vec()[0].created_at().as_secs())

        if show_history:
            nutzap_wallet_client.print_transaction_history(transactions.to_vec(), keys)

    nut_zap_history_filter = Filter().pubkey(keys.public_key()).kinds([Kind(9321)]).since(from_time).custom_tag(
        SingleLetterTag.lowercase(Alphabet.U),
        mints)

    # hist_events = await client.get_events_of([nut_zap_history_filter], timedelta(10))

    # nut_zap_filter = Filter().pubkey(keys.public_key()).kinds([Kind(9321)]).custom_tag(
    #    SingleLetterTag.lowercase(Alphabet.U),
    #    mints)
    set_profile = True
    if set_profile:
        lud16 = "hype@bitcoinfixesthis.org"  # overwrite with your ln address
        await nutzap_wallet_client.set_profile("Test", "I'm a nutsack test account", lud16,
                                        "https://i.nostr.build/V4FwExrV5aXHNm70.jpg", client, keys)

    print("PrivateKey: " + keys.secret_key().to_bech32() + " PublicKey: " + keys.public_key().to_bech32())
    # See if we already have a wallet and fetch it
    nut_wallet = await nutzap_wallet_client.get_nut_wallet(client, keys)

    if nut_wallet is None:
        await nutzap_wallet_client.create_new_nut_wallet(mints, relays, client, keys, "Test", "My Nutsack")
        nut_wallet = await nutzap_wallet_client.get_nut_wallet(client, keys)
        if nut_wallet is not None:
            await nutzap_wallet_client.announce_nutzap_info_event(nut_wallet, client, keys)
        else:
            print("Couldn't fetch wallet, please restart and see if it is there")

    await client.subscribe([nut_zap_history_filter], None)



    class NotificationHandler(HandleNotification):
        async def handle(self, relay_url, subscription_id, event: Event):
            # print(f"Received new event from {relay_url}: {event.as_json()}")

            # If we receive a nutzap addressed to us, with our mints, we claim the proofs
            if event.kind().as_u16() == 9321:
                print(bcolors.YELLOW + "[Client] NutZap 🥜️⚡ received" + event.as_json() + bcolors.ENDC)

                # if event.author().to_hex() == keys.public_key().to_hex():
                #     #sleep to avoid event not being updated on self zap
                #     await asyncio.sleep(5)

                nut_wallet = await nutzap_wallet_client.get_nut_wallet(client, keys)
                if nut_wallet is not None:
                    await nutzap_wallet_client.reedeem_nutzap(event, nut_wallet, client, keys)
                    # await get_nut_wallet(client, keys)

        async def handle_msg(self, relay_url, msg):
            return

    asyncio.create_task(client.handle_notifications(NotificationHandler()))
    while True:
        await asyncio.sleep(2.0)


if __name__ == '__main__':
    env_path = Path('.env')
    if env_path.is_file():
        print(f'loading environment from {env_path.resolve()}')
        dotenv.load_dotenv(env_path, verbose=True, override=True)
    else:
        raise FileNotFoundError(f'.env file not found at {env_path} ')

    relays = ["wss://relay.primal.net"]
    mints = ["https://mint.gwoq.com"]
    show_history = True

    asyncio.run(nostr_client(relays, mints, show_history))
