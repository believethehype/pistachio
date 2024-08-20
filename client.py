import asyncio
from datetime import timedelta
from pathlib import Path

import dotenv
from nostr_sdk import HandleNotification, Event, Filter, SingleLetterTag, Alphabet, Kind, Timestamp, EventSource

from nut_wallet_utils import NutZapWallet
from nostr_dvm.utils.print import bcolors

async def nostr_client(relays, mints, show_history):
    nutzap_wallet_client = NutZapWallet()
    client, keys, = await nutzap_wallet_client.client_connect(relays)

    # per default, check events within the last 60 seconds
    from_time = Timestamp.from_secs(Timestamp.now().as_secs() - 60)

    # but eventually, we check all events since the last time a transaction was made
    # therefore we fetch the transaction history (Maybe we limit this to 1 in the future)
    transaction_history_filter = Filter().author(keys.public_key()).kinds([Kind(7376)])  # .limit(1)
    source = EventSource.relays(timedelta(seconds=10))
    transactions = await client.get_events_of([transaction_history_filter],source)

    # If we find transactions, we look for all events since right after the last one
    print("\n" + bcolors.CYAN + "Transaction History:" + bcolors.ENDC)
    if len(transactions) > 0:
        from_time = Timestamp.from_secs(transactions[0].created_at().as_secs())

        if show_history:
            nutzap_wallet_client.print_transaction_history(transactions, keys)

    nut_zap_history_filter = Filter().pubkey(keys.public_key()).kinds([Kind(9321)]).since(from_time).custom_tag(
        SingleLetterTag.lowercase(Alphabet.U),
        mints)

    #hist_events = await client.get_events_of([nut_zap_history_filter], timedelta(10))

    #nut_zap_filter = Filter().pubkey(keys.public_key()).kinds([Kind(9321)]).custom_tag(
    #    SingleLetterTag.lowercase(Alphabet.U),
    #    mints)

    await client.subscribe([nut_zap_history_filter], None)

    class NotificationHandler(HandleNotification):
        async def handle(self, relay_url, subscription_id, event: Event):
            # print(f"Received new event from {relay_url}: {event.as_json()}")

            # If we receive a nutzap addressed to us, with our mints, we claim the proofs
            if event.kind().as_u64() == 9321:
                print(bcolors.CYAN + "[Client] " + event.as_json() + bcolors.ENDC)

                #if event.author().to_hex() == keys.public_key().to_hex():
                #     #sleep to avoid event not being updated on self zap
                #     await asyncio.sleep(5)

                nut_wallet = await nutzap_wallet_client.get_nut_wallet(client, keys)
                if nut_wallet is not None:
                    await nutzap_wallet_client.reedeem_nutzap(event, nut_wallet, client, keys)
                    #await get_nut_wallet(client, keys)

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
    mints = ["https://mint.minibits.cash/Bitcoin", "https://mint.gwoq.com"]
    show_history = True

    asyncio.run(nostr_client(relays, mints, show_history))