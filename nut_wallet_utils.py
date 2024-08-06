import json
import os
from datetime import timedelta
from hashlib import sha256

import requests
from cashu.core.base import Proof
from cashu.wallet.wallet import Wallet
from nostr_dvm.utils.definitions import EventDefinitions
from nostr_dvm.utils.dvmconfig import DVMConfig
from nostr_dvm.utils.nostr_utils import send_event, check_and_set_private_key
from nostr_dvm.utils.zap_utils import pay_bolt11_ln_bits
from nostr_sdk import Tag, Keys, nip44_encrypt, nip44_decrypt, Nip44Version, EventBuilder, Client, Filter, Nip19, Kind, \
    EventId, nip04_decrypt, nip04_encrypt, Options, NostrSigner, PublicKey
from nostr_dvm.utils.print import bcolors

import cashu_utils


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
    proof: Proof
    a: str
    previous_event_id: EventId


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
    return client, dvmconfig, keys


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
                elif tag.as_vec()[0] == "a":
                    a = tag.as_vec()[1]
                    print("a: " + a)

            for proof in proofs_json['proofs']:
                nut_proof = NutProof()
                nut_proof.proof = Proof()
                nut_proof.proof.id = proof['id']
                nut_proof.proof.secret = proof['secret']
                nut_proof.proof.amount = proof['amount']
                nut_proof.proof.C = proof['C']
                nut_proof.proof.mint_id = mint
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


    d_tag = Tag.parse(["d", nut_wallet.d])
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


async def create_unspent_proof_event(nut_wallet: NutWallet, mint_proofs, mint_url, client, dvm_config):
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

    print(message)
    if nut_wallet.legacy_encryption:
        content = nip04_encrypt(keys.secret_key(), keys.public_key(), message)
    else:
        content = nip44_encrypt(keys.secret_key(), keys.public_key(), message, Nip44Version.V2)

    event = EventBuilder(Kind(7375), content, tags).to_event(keys)
    eventid = await send_event(event, client=client, dvm_config=dvm_config)
    return amount


async def mint_token(mint, amount):
    url = mint + "/v1/mint/quote/bolt11"
    json_object = {"unit": "sat", "amount": amount}

    headers = {"Content-Type": "application/json; charset=utf-8"}
    request_body = json.dumps(json_object).encode('utf-8')
    request = requests.post(url, data=request_body, headers=headers)
    tree = json.loads(request.text)

    config = DVMConfig()
    config.LNBITS_ADMIN_KEY = os.getenv("LNBITS_ADMIN_KEY")
    config.LNBITS_URL = os.getenv("LNBITS_HOST")
    paymenthash = pay_bolt11_ln_bits(tree["request"], config)
    print(paymenthash)
    url = f"{mint}/v1/mint/quote/bolt11/{tree['quote']}"

    response = requests.get(url, data=request_body, headers=headers)
    tree2 = json.loads(response.text)
    if tree2["paid"]:
        print(response.text)
        wallet = await Wallet.with_db(
            url=mint,
            db="db/Cashu",
        )

        await wallet.load_mint()
        proofs = await wallet.mint(amount, tree['quote'], None)
        return proofs


async def announce_nutzap_info_event(mints, relays, nut_wallet):
    client, dvm_config, keys, = await client_connect(relays)

    tags = []
    for relay in relays:
        tags.append(Tag.parse(["relay", relay]))
    for mint in mints:
        tags.append(Tag.parse(["mint", mint]))

    cashu_wallet = await Wallet.with_db(
        url=mints[0],
        db="db/Cashu",
        name="wallet_mint_api",
    )

    await cashu_wallet.load_mint()

    # todo what is the pubkey?
    # p2pkpubkey = await cashu_wallet.create_p2pk_pubkey()
    pubkey = Keys.parse(nut_wallet.privkey).public_key().to_hex()

    tags.append(Tag.parse(["pubkey", pubkey]))

    event = EventBuilder(Kind(10019), "", tags).to_event(keys)
    eventid = await send_event(event, client=client, dvm_config=dvm_config)


async def fetch_mint_info_event(pubkey, relays):
    client, dvm_config, keys, = await client_connect(relays)

    mint_info_filter = Filter().kind(Kind(10019)).author(PublicKey.parse(pubkey))
    preferences = await client.get_events_of([mint_info_filter], timedelta(5))
    mints = []
    relays = []
    pubkey = ""

    if len(preferences) > 0:
        # TODO make sure it's latest
        preference = preferences[0]

        for tag in preference.tags():
            if tag.as_vec()[0] == "pubkey":
                pubkey = tag.as_vec()[1]
            elif tag.as_vec()[0] == "relay":
                relays.append(tag.as_vec()[1])
            elif tag.as_vec()[0] == "mint":
                mints.append(tag.as_vec()[1])

    return pubkey, mints, relays


async def update_mint_proof_event(nut_wallet, send_proofs, relays):
    event_id = ""
    mint = ""
    print(nut_wallet.proofs)
    print(send_proofs)
    amount = 0
    for send_proof in send_proofs:
        entry = [x for x in nut_wallet.proofs if x.proof.id == send_proof.id]
        if len(entry) > 0:
            nut_wallet.proofs.remove(entry[0])
            event_id = entry[0].previous_event_id
            mint = entry[0].proof.mint_id
        amount += send_proof.amount




    client, dvm_config, keys, = await client_connect(relays)

    #update wallet balance
    await update_nut_wallet(nut_wallet, mint, -amount, relays)

    # Delete old event
    evt = EventBuilder.delete([event_id], reason="deleted").to_event(keys)
    await client.send_event(evt)


    proofs = []
    for proof in nut_wallet.proofs:
        proofs.append(proof.proof)
    # create new event
    await create_unspent_proof_event(nut_wallet, proofs, mint, client, dvm_config)
    return nut_wallet


async def send_nut_zap(amount, comment, nut_wallet: NutWallet, zapped_event, zapped_user, lookup_relays):
    client, dvm_config, keys, = await client_connect(lookup_relays)

    unit = "sat"
    p2pk_pubkey, mints, relays = await fetch_mint_info_event(zapped_user, lookup_relays)

    if len(mints) == 0:
        print("No preferred mint set, returing")
        return

    mint = mints[11]

    tags = []
    tags.append(Tag.parse(["amount", str(amount), unit]))
    tags.append(Tag.parse(["comment", comment]))
    tags.append(Tag.parse(["u", mint]))
    tags.append(Tag.parse(["e", zapped_event]))
    tags.append(Tag.parse(["p", zapped_user]))

    # todo some advanced logic to build the requested amount
    # todo maybe just hold cashu proofs in the first place
    selected_proof = None
    cashu_proofs = []
    for nut_proof in nut_wallet.proofs:
        # cashu_proof = Proof()
        # cashu_proof.id = proof.id
        # cashu_proof.amount = proof.amount
        # cashu_proof.secret = proof.secret
        # cashu_proof.C = proof.C
        cashu_proofs.append(nut_proof.proof)

    cashu_wallet = await Wallet.with_db(
        url=mint,
        db="db/Cashu",
        name="wallet_mint_api",
    )

    # TODO this doesn't work yet

    await cashu_wallet.load_mint()

    # p2pk test
    secret_lock = await cashu_wallet.create_p2pk_lock("02" + p2pk_pubkey)  # sender side
    print(secret_lock)

    # item_to_remove = [x for x in cashu_proofs if
    #                  x.secret == "4ce3a5a98a1c8854162e07985096b507de86486c70d241c4fe6bcd015fb2a72f"]
    # nut_wallet.proofs.remove(item_to_remove[0])
    # cashu_proofs.remove(item_to_remove[0])

    try:
        _, send_proofs = await cashu_wallet.swap_to_send(
            cashu_proofs, amount, secret_lock=secret_lock
        )
        print(_)
        print(send_proofs)

        # TODO remove send_proofs from nut_wallet.proofs... somehow

        try:
            nut_wallet = await update_mint_proof_event(nut_wallet, send_proofs, relays)
        except Exception as e:
            print(e)
        if cashu_wallet.available_balance == 0:
            print("nah")
        # mint_token()
        print(cashu_wallet.available_balance)
        # proofs, fees = await cashu_wallet.select_to_send(cashu_proofs, amount)

        send_proofs_json = []
        for proof in send_proofs:
            nut_proof = {
                'id': proof.id,
                'C': proof.C,
                'amount': proof.amount,
                'secret': proof.secret,
            }
            send_proofs_json.append(nut_proof)

        content = json.dumps(send_proofs_json)
        event = EventBuilder(Kind(10019), content, tags).to_event(keys)
        eventid = await send_event(event, client=client, dvm_config=dvm_config)

    except Exception as e:
        print(e)

    # print(json.dumps(send_proofs))
    # print(content)
    # await wallet2.redeem(send_proofs)

    # proof_states = await wallet2.check_proof_state(send_proofs)

    # p2pksecret = await cashu_wallet.create_p2pk_lock("02" + p2pk_pubkey)

    # p2pksecret.to
    # signed_proofs = await cashu_wallet.sign_p2pk_proofs(proofs)

    # TODO p2pk magic

    # content = "[{\"amount\":1,\"C\":\"02277c66191736eb72fce9d975d08e3191f8f96afb73ab1eec37e4465683066d3f\",\"id\":\"000a93d6f8a1d2c4\",\"secret\":\"[\\\"P2PK\\\",{\\\"nonce\\\":\\\"b00bdd0467b0090a25bdf2d2f0d45ac4e355c482c1418350f273a04fedaaee83\\\",\\\"data\\\":\\\"02eaee8939e3565e48cc62967e2fde9d8e2a4b3ec0081f29eceff5c64ef10ac1ed\\\"}]\"}]"
