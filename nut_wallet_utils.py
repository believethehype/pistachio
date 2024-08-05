import json
from datetime import timedelta
from hashlib import sha256

from nostr_dvm.utils.definitions import EventDefinitions
from nostr_dvm.utils.nostr_utils import send_event
from nostr_sdk import Tag, Keys, nip44_encrypt, nip44_decrypt, Nip44Version, EventBuilder, Client, Filter, Nip19, Kind, \
    EventId, nip04_decrypt
from nostr_dvm.utils.print import bcolors


class NutWallet:
    name: str
    description: str
    balance: int
    unit: str
    mints: list = []
    relays: list = []
    proofs: list = []
    privkey: str
    d: str
    a: str


class NutProof:
    id: str
    amount: int
    secret: str
    C: str
    mint: str
    previous_event_id: EventId


async def get_nut_wallet(client: Client, keys: Keys) -> NutWallet:
    nutwallet = None

    wallet_filter = Filter().kind(EventDefinitions.KIND_NUT_WALLET).author(keys.public_key())
    wallets = await client.get_events_of([wallet_filter], timedelta(5))

    if len(wallets) > 0:
        nutwallet = NutWallet()
        latest = 0
        best_wallet = None
        for wallet_event in wallets:

            isdeleted = False
            for tag in wallet_event.tags():
                if tag.as_vec()[0] == "deleted":
                    isdeleted = True
                    break
            if isdeleted:
                continue
            else:
                if wallet_event.created_at().as_secs() > latest:
                    latest = wallet_event.created_at().as_secs()
                    best_wallet = wallet_event

        try:
            content = nip44_decrypt(keys.secret_key(), keys.public_key(), best_wallet.content())
            print(content)
        except:
            content = nip04_decrypt(keys.secret_key(), keys.public_key(), best_wallet.content())
            print(content)
            print("we have a nip04 enconding.. ")

        inner_tags = json.loads(content)
        for tag in inner_tags:
            # These tags must be encrypted instead of in the outer tags
            if tag[0] == "balance":
                nutwallet.balance = int(tag[1])
            elif tag[0] == "privkey":
                nutwallet.privkey = tag[1]
            # These tags can be encrypted instead of in the outer tags
            elif tag[0] == "name":
                nutwallet.name = tag[1]
            elif tag[0] == "description":
                nutwallet.description = tag[1]
            elif tag[0] == "unit":
                nutwallet.unit = tag[1]
            elif tag[0] == "relay":
                nutwallet.relays.append(tag[1])
            elif tag[0] == "mint":
                nutwallet.mints.append(tag[1])

        for tag in best_wallet.tags():
            if tag.as_vec()[0] == "d":
                nutwallet.d = tag.as_vec()[1]
            # These tags can be in the outer tags (if not encrypted)
            elif tag.as_vec()[0] == "name":
                nutwallet.name = tag.as_vec()[1]
            elif tag.as_vec()[0] == "description":
                nutwallet.description = tag.as_vec()[1]
            elif tag.as_vec()[0] == "unit":
                nutwallet.unit = tag.as_vec()[1]
            elif tag.as_vec()[0] == "relay":
                nutwallet.relays.append(tag.as_vec()[1])
            elif tag.as_vec()[0] == "mint":
                nutwallet.mints.append(tag.as_vec()[1])

        # Now get proofs
        proof_filter = Filter().kind(EventDefinitions.KIND_NIP60_NUT_PROOF).author(keys.public_key())
        proof_events = await client.get_events_of([proof_filter], timedelta(5))

        for proof_event in proof_events:
            content = nip44_decrypt(keys.secret_key(), keys.public_key(), proof_event.content())
            proofs_json = json.loads(content)
            mint = ""
            for entry in proofs_json:
                if entry[0] == "mint":
                    mint = entry[1]
                    print("mint: " + entry[1])
                    break

            for entry in proofs_json:
                if entry[0] == "proofs":
                    proofs = json.loads(entry[1])
                    for proof in proofs:
                        nut_proof = NutProof()
                        nut_proof.id = proof['id']
                        nut_proof.secret = proof['secret']
                        nut_proof.amount = proof['amount']
                        nut_proof.C = proof['C']
                        nut_proof.mint = mint
                        nut_proof.previous_event_id = proof_event.id()
                        nutwallet.proofs.append(nut_proof)

            # evt = EventBuilder.delete([proof_event.id()], reason="deleted").to_event(keys)
            # await client.send_event(evt)

        nutwallet.a = str(
            EventDefinitions.KIND_NUT_WALLET.as_u64()) + ":" + best_wallet.author().to_hex() + ":" + nutwallet.d  # TODO maybe this is wrong
    return nutwallet


async def create_nut_wallet(nut_wallet: NutWallet, client, dvm_config):
    innertags = []
    balance_tag = Tag.parse(["balance", str(nut_wallet.balance), nut_wallet.unit])
    prikey_tag = Tag.parse(["privkey", nut_wallet.privkey])
    innertags.append(balance_tag.as_vec())
    innertags.append(prikey_tag.as_vec())

    keys = Keys.parse(dvm_config.PRIVATE_KEY)
    print(keys.secret_key().to_bech32())

    content = nip44_encrypt(keys.secret_key(), keys.public_key(), json.dumps(innertags), Nip44Version.V2)

    tags = []

    name_tag = Tag.parse(["name", nut_wallet.name])
    tags.append(name_tag)

    unit_tag = Tag.parse(["unit", nut_wallet.unit])
    tags.append(unit_tag)

    descriptipn_tag = Tag.parse(["description", nut_wallet.description])
    tags.append(descriptipn_tag)

    key_str = str(nut_wallet.name + nut_wallet.description)
    d = sha256(key_str.encode('utf-8')).hexdigest()[:16]
    d_tag = Tag.parse(["d", d])
    tags.append(d_tag)

    for mint in nut_wallet.mints:
        mint_tag = Tag.parse(["mint", mint])
        tags.append(mint_tag)

    for relay in nut_wallet.relays:
        relay_tag = Tag.parse(["relay", relay])
        tags.append(relay_tag)

    event = EventBuilder(EventDefinitions.KIND_NUT_WALLET, content, tags).to_event(keys)
    eventid = await send_event(event, client=client, dvm_config=dvm_config)

    print(
        bcolors.BLUE + "[" + nut_wallet.name + "] Announced NIP 60 for Wallet (" + eventid.id.to_hex() + ")" + bcolors.ENDC)


async def create_unspent_proof_event(nut_wallet: NutWallet, mint_proofs_list, mint_url, client, dvm_config):
    innertags = []
    mint_tag = Tag.parse(["mint", mint_url])
    innertags.append(mint_tag.as_vec())
    new_proofs = []

    for mint_proofs in mint_proofs_list:
        for proof in mint_proofs:
            if not any(x.id == proof.id for x in nut_wallet.proofs):
                proofjson = {
                    "id": proof.id,
                    "amount": proof.amount,
                    "secret": proof.secret,
                    "C": proof.C
                }
                new_proofs.append(proofjson)
                nut_wallet.proofs.append(proof)

        if len(new_proofs) == 0:
            return

        # TODO otherwise delete previous event and make new one, I guess

        proofs_tag = Tag.parse(["proofs", json.dumps( nut_wallet.proofs)])
        innertags.append(proofs_tag.as_vec())

        tags = []
        print(nut_wallet.a)
        a_tag = Tag.parse(["a", nut_wallet.a])
        tags.append(a_tag)

        keys = Keys.parse(dvm_config.PRIVATE_KEY)
        content = nip44_encrypt(keys.secret_key(), keys.public_key(), json.dumps(innertags), Nip44Version.V2)

        event = EventBuilder(Kind(7375), content, tags).to_event(keys)
        eventid = await send_event(event, client=client, dvm_config=dvm_config)
