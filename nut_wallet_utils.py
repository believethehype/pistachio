import json
import os
from datetime import timedelta
from hashlib import sha256

import requests
from cashu.wallet.wallet import Wallet
from nostr_dvm.utils.definitions import EventDefinitions
from nostr_dvm.utils.dvmconfig import DVMConfig
from nostr_dvm.utils.nostr_utils import send_event
from nostr_dvm.utils.zap_utils import pay_bolt11_ln_bits
from nostr_sdk import Tag, Keys, nip44_encrypt, nip44_decrypt, Nip44Version, EventBuilder, Client, Filter, Nip19, Kind, \
    EventId, nip04_decrypt, nip04_encrypt
from nostr_dvm.utils.print import bcolors


class NutWallet:
    name: str = "NutWallet"
    description: str = ""
    balance: int
    unit: str = "sat"
    mints: list = []
    relays: list = []
    proofs: list = []
    privkey: str
    d: str
    a: str
    legacy_encryption: bool = False


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
            nutwallet.legacy_encryption = True

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
            try:
                content = nip44_decrypt(keys.secret_key(), keys.public_key(), proof_event.content())
            except:
                content = nip04_decrypt(keys.secret_key(), keys.public_key(), proof_event.content())
                print("we have a nip04 enconding for proofs.. ")
                print(content)

            proofs_json = json.loads(content)
            mint = ""

            try:
                mint = proofs_json['mint']
                print("mint: " + mint)
                a = proofs_json['a']
                print("a: " + a)
            except:
                print("tags not private, looking in public tags")

            for tag in proof_event.tags():
                if tag.as_vec()[0] == "mint":
                    mint = tag.as_vec()[1]
                    print("mint: " + mint)
                if tag.as_vec()[0] == "a":
                    a = tag.as_vec()[1]
                    print("a: " + a)

            for proof in proofs_json['proofs']:
                nut_proof = NutProof()
                nut_proof.id = proof['id']
                nut_proof.secret = proof['secret']
                nut_proof.amount = proof['amount']
                nut_proof.C = proof['C']
                nut_proof.mint = mint
                nut_proof.previous_event_id = proof_event.id()
                nut_proof.a = a
                nutwallet.proofs.append(nut_proof)
                print(proof)

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
    if nut_wallet.legacy_encryption:
        content = nip04_encrypt(keys.secret_key(), keys.public_key(), json.dumps(innertags))
    else:
        content = nip44_encrypt(keys.secret_key(), keys.public_key(), json.dumps(innertags), Nip44Version.V2)

    tags = []

    name_tag = Tag.parse(["name", nut_wallet.name])
    tags.append(name_tag)

    if nut_wallet.unit is None:
        nut_wallet.unit = "sat"

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


async def create_unspent_proof_event(nut_wallet: NutWallet, mint_proofs, mint_url, client, dvm_config):
    #innertags = []
    #mint_tag = Tag.parse(["mint", mint_url])
    #innertags.append(mint_tag.as_vec())
    new_proofs = []
    amount = 0
    for proof in mint_proofs:
        proofjson = {
            "id": proof['id'],
            "amount": proof['amount'],
            "secret": proof['secret'],
            "C": proof['C']
        }
        amount += int(proof['amount'])
        new_proofs.append(proofjson)

    # TODO otherwise delete previous event and make new one, I guess

    #proofs_tag = Tag.parse(["proofs", json.dumps(new_proofs)])
    #innertags.append(proofs_tag.as_vec())

    tags = []
    print(nut_wallet.a)
    a_tag = Tag.parse(["a", nut_wallet.a])
    tags.append(a_tag)

    keys = Keys.parse(dvm_config.PRIVATE_KEY)
    j = {
        "mint": mint_url,
        "proofs": new_proofs
    }

    message = json.dumps(j)


    #json.dumps(innertags)
    print(message)
    if nut_wallet.legacy_encryption:
        content = nip04_encrypt(keys.secret_key(), keys.public_key(), message)
    else:
        content = nip44_encrypt(keys.secret_key(), keys.public_key(), message, Nip44Version.V2)

    event = EventBuilder(Kind(7375), content, tags).to_event(keys)
    eventid = await send_event(event, client=client, dvm_config=dvm_config)
    return amount
