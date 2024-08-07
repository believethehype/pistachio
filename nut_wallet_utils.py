import asyncio
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
    EventId, nip04_decrypt, nip04_encrypt, Options, NostrSigner, PublicKey, init_logger, LogLevel
from nostr_dvm.utils.print import bcolors

init_logger(LogLevel.ERROR)


class NutWallet:
    name: str = "NutWallet"
    description: str = ""
    balance: int
    unit: str = "sat"
    mints: list = []
    relays: list = []
    nutmints: list = []
    privkey: str
    d: str
    a: str
    legacy_encryption: bool = True  # Use Nip04 instead of Nip44, for reasons, turn to False ASAP.


class NutMint:
    proofs: list = []
    mint_url: str
    previous_event_id: EventId
    a: str

    def available_balance(self):
        balance = 0
        for proof in self.proofs:
            balance += proof.amount
        return balance


async def client_connect(relay_list):
    dvmconfig = DVMConfig()
    dvmconfig.RELAY_LIST = relay_list

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


async def create_new_nut_wallet(mint_urls, relays, name, description):
    client, dvm_config, keys, = await client_connect(relays)
    dvm_config = DVMConfig()
    dvm_config.RELAY_LIST = relays
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
    print("Creating Wallet..")
    await create_nut_wallet(new_nut_wallet, client, dvm_config)

    print(new_nut_wallet.name + ": " + str(new_nut_wallet.balance) + " " + new_nut_wallet.unit + " Mints: " + str(
        new_nut_wallet.mints) + " Key: " + new_nut_wallet.privkey)

    return new_nut_wallet


async def get_nut_wallet(relays) -> NutWallet:
    client, dvm_config, keys, = await client_connect(relays)
    print(keys.secret_key().to_bech32())

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
            print("Warning: This Wallet is using a NIP04 enconding.., it should use NIP44 encoding ")
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
        proof_filter = Filter().kind(Kind(7375)).author(keys.public_key())
        proof_events = await client.get_events_of([proof_filter], timedelta(5))

        for proof_event in proof_events:
            try:
                content = nip44_decrypt(keys.secret_key(), keys.public_key(), proof_event.content())
            except:
                content = nip04_decrypt(keys.secret_key(), keys.public_key(), proof_event.content())
                print("Warning: This Proofs event is using a NIP04 enconding.., it should use NIP44 encoding ")

            proofs_json = json.loads(content)
            mint_url = ""
            a = ""
            print("")
            print("AVAILABLE MINT:")

            # print(proof_event.id().to_hex())
            try:
                mint_url = proofs_json['mint']
                print("mint: " + mint_url)
                a = proofs_json['a']
                print("a: " + a)
            except Exception as e:
                pass

            for tag in proof_event.tags():
                if tag.as_vec()[0] == "mint":
                    mint_url = tag.as_vec()[1]
                    print("mint: " + mint_url)
                elif tag.as_vec()[0] == "a":
                    a = tag.as_vec()[1]
                    print("a: " + a)

            nut_mint = NutMint()
            nut_mint.mint_url = mint_url
            nut_mint.a = a
            nut_mint.previous_event_id = proof_event.id()
            nut_mint.proofs = []

            for proof in proofs_json['proofs']:
                proofs = [x for x in nut_mint.proofs if x.secret == proof['secret']]
                if len(proofs) == 0:
                    nut_proof = Proof()
                    nut_proof.id = proof['id']
                    nut_proof.secret = proof['secret']
                    nut_proof.amount = proof['amount']
                    nut_proof.C = proof['C']
                    nut_mint.proofs.append(nut_proof)
                    print(proof)

            mints = [x for x in nutwallet.nutmints if x.mint_url == mint_url]
            if len(mints) == 0:
                nutwallet.nutmints.append(nut_mint)

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
    dvm_config.RELAY_LIST = relays
    dvm_config.PRIVATE_KEY = keys.secret_key().to_hex()

    nut_wallet.balance = int(nut_wallet.balance) + int(additional_amount)
    if mint not in nut_wallet.mints:
        nut_wallet.mints.append(mint)
    await create_nut_wallet(nut_wallet, client, dvm_config)

    print(nut_wallet.name + ": " + str(nut_wallet.balance) + " " + nut_wallet.unit + " Mints: " + str(
        nut_wallet.mints) + " Key: " + nut_wallet.privkey)

    return nut_wallet


def get_mint(nut_wallet, mint_url) -> NutMint:
    mints = [x for x in nut_wallet.nutmints if x.mint_url == mint_url]
    if len(mints) == 0:
        mint = NutMint()
        mint.proofs = []
        mint.previous_event_id = None
        mint.a = nut_wallet.a
        mint.mint_url = mint_url
        nut_wallet.nutmints.append(mint)
    else:
        mint = mints[0]

    return mint


async def create_unspent_proof_event(nut_wallet: NutWallet, mint_proofs, mint_url, relays):
    client, dvm_config, keys, = await client_connect(relays)

    new_proofs = []
    amount = 0

    mint = get_mint(nut_wallet, mint_url)
    mint.proofs = mint_proofs
    for proof in mint_proofs:
        proofjson = {
            "id": proof['id'],
            "amount": proof['amount'],
            "secret": proof['secret'],
            "C": proof['C']
        }
        print(proof)
        amount += int(proof['amount'])
        new_proofs.append(proofjson)

    if mint.previous_event_id is not None:
        print(
            bcolors.RED + "[" + nut_wallet.name + "] Deleting previous proofs event.. : (" + mint.previous_event_id.to_hex() + ")" + bcolors.ENDC)
        evt = EventBuilder.delete([mint.previous_event_id], reason="deleted").to_event(keys)  # .to_pow_event(keys, 28)
        response = await client.send_event(evt)
        # print(response.id.to_hex())

    tags = []
    print(nut_wallet.a)
    a_tag = Tag.parse(["a", nut_wallet.a])
    tags.append(a_tag)

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
    print(
        bcolors.GREEN + "[" + nut_wallet.name + "] Sent new proofs event.. : (" + eventid.id.to_hex() + ")" + bcolors.ENDC)

    return eventid.id


async def mint_token(mint, amount):
    url = mint + "/v1/mint/quote/bolt11"
    json_object = {"unit": "sat", "amount": amount}

    headers = {"Content-Type": "application/json; charset=utf-8"}
    request_body = json.dumps(json_object).encode('utf-8')
    request = requests.post(url, data=request_body, headers=headers)
    tree = json.loads(request.text)

    config = DVMConfig()
    config.RELAY_LIST = []
    config.LNBITS_ADMIN_KEY = os.getenv("LNBITS_ADMIN_KEY")
    config.LNBITS_URL = os.getenv("LNBITS_HOST")
    paymenthash = pay_bolt11_ln_bits(tree["request"], config)
    print(paymenthash)
    url = f"{mint}/v1/mint/quote/bolt11/{tree['quote']}"

    response = requests.get(url, data=request_body, headers=headers)
    tree2 = json.loads(response.text)
    waitfor = 5
    while not tree2["paid"]:
        await asyncio.sleep(1)
        response = requests.get(url, data=request_body, headers=headers)
        tree2 = json.loads(response.text)
        waitfor -= 1
        if waitfor == 0:
            break

    if tree2["paid"]:
        print(response.text)
        wallet = await Wallet.with_db(
            url=mint,
            db="db/Cashu",
        )

        await wallet.load_mint()
        proofs = await wallet.mint(amount, tree['quote'], None)
        return proofs


async def announce_nutzap_info_event(nut_wallet, additional_relays=None):
    if additional_relays is None:
        additional_relays = []
    for relay in nut_wallet.relays:
        if relay not in additional_relays:
            additional_relays.append(relay)

    client, dvm_config, keys, = await client_connect(additional_relays)

    tags = []
    for relay in nut_wallet.relays:
        tags.append(Tag.parse(["relay", relay]))
    for mint in nut_wallet.mints:
        tags.append(Tag.parse(["mint", mint]))

    cashu_wallet = await Wallet.with_db(
        url=nut_wallet.mints[0],
        db="db/Cashu",
        name="wallet_mint_api",
    )
    await cashu_wallet.load_mint()
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


async def update_mint_proof_event(nut_wallet, send_proofs, mint_url, relays):
    mint = get_mint(nut_wallet, mint_url)

    print(mint.mint_url)
    print(send_proofs)
    amount = 0
    for send_proof in send_proofs:
        entry = [x for x in mint.proofs if x.id == send_proof.id and x.secret == send_proof.secret]
        if len(entry) > 0:
            mint.proofs.remove(entry[0])
            amount += send_proof.amount

    client, dvm_config, keys, = await client_connect(relays)

    # TODO create and add send_proofs to 7376 history event

    # create new event
    mint.previous_event_id = await create_unspent_proof_event(nut_wallet, mint.proofs, mint.mint_url, relays)
    nut_wallet = await update_nut_wallet(nut_wallet, mint.mint_url, -amount, relays)

    return nut_wallet


async def mint_cashu(nut_wallet: NutWallet, mint_url, relays, amount):
    print("Minting new tokens on: " + mint_url)
    # Mint the Token at the selected mint
    proofs = await mint_token(mint_url, amount)
    print(proofs)
    additional_amount = 0

    mint = get_mint(nut_wallet, mint_url)
    # store the new proofs in proofs_temp
    all_proofs = []

    # check for other proofs from same mint, add them to the list of proofs
    for nut_proof in mint.proofs:
        all_proofs.append(nut_proof)
    # add new proofs and calculate additional balance
    for proof in proofs:
        additional_amount += proof.amount
        all_proofs.append(proof)

    print("additional amount: " + str(additional_amount))
    mint.previous_event_id = await create_unspent_proof_event(nut_wallet, all_proofs, mint_url, relays)

    return await update_nut_wallet(nut_wallet, mint_url, additional_amount, relays)
    # return await get_nut_wallet(client, keys)


async def send_nut_zap(amount, comment, nut_wallet: NutWallet, zapped_event, zapped_user, lookup_relays):
    client, dvm_config, keys, = await client_connect(lookup_relays)

    unit = "sat"
    p2pk_pubkey, mints, relays = await fetch_mint_info_event(zapped_user, lookup_relays)

    if len(mints) == 0:
        print("No preferred mint set, returing")
        return

    mint_success = False
    index = 0
    mint_url = ""
    fees = 0 # Don't know, is this something to consider?
    sufficent_budget = False

    # Some logic.
    # First look if we have balance on a mint the user has in their list of trusted mints and use it
    for mint in nut_wallet.nutmints:
        if mint.available_balance() > amount and mint.mint_url in mints:
            mint_url = mint.mint_url
            sufficent_budget = True
            break
    # If that's not the case, lets look or mints we both trust, take the first one.
    if not sufficent_budget:
        mint_url = next(i for i in nut_wallet.mints if i in mints)
        mint = get_mint(nut_wallet, mint_url)
        if mint.available_balance() < amount + fees:
            mint_amount = amount + fees - mint.available_balance()
            await mint_cashu(nut_wallet, mint_url, lookup_relays, mint_amount)

        # If that's not the case, iterate over the recipents mints and try to mint there. This might be a bit dangerous as not all mints might give cashu, so loss of ln is possible
        if mint_url is None:
            while not mint_success:
                try:
                    mint_url = mints[index]  #
                    # Maybe we introduce a list of known failing mints..
                    if mint_url == "https://stablenut.umint.cash":
                        raise Exception("stablemint bad")
                    mint = get_mint(nut_wallet, mint_url)
                    if mint.available_balance() < amount + fees:
                        mint_amount = amount + fees - mint.available_balance()
                        await mint_cashu(nut_wallet, mint_url, lookup_relays, mint_amount)
                    mint_success = True
                except:
                    mint_success = False
                    index += 1

    tags = [Tag.parse(["amount", str(amount)]),
            Tag.parse(["unit", unit]),
            Tag.parse(["u", mint_url]),
            Tag.parse(["p", zapped_user])]

    if zapped_event != "":
        tags.append(Tag.parse(["e", zapped_event]))

    mint = get_mint(nut_wallet, mint_url)

    cashu_wallet = await Wallet.with_db(
        url=mint_url,
        db="db/Cashu",
        name="wallet_mint_api",
    )

    await cashu_wallet.load_mint()
    secret_lock = await cashu_wallet.create_p2pk_lock("02" + p2pk_pubkey)  # sender side

    try:
        # print(cashu_proofs)
        proofs, fees = await cashu_wallet.select_to_send(mint.proofs, amount)
        _, send_proofs = await cashu_wallet.swap_to_send(
            proofs, amount, secret_lock=secret_lock, set_reserved=True
        )
        # print(send_proofs)

        try:
            await update_mint_proof_event(nut_wallet, proofs, mint_url, lookup_relays)
        except Exception as e:
            print(e)

        send_proofs_json = []
        for proof in send_proofs:
            nut_proof = {
                'id': proof.id,
                'C': proof.C,
                'amount': proof.amount,
                'secret': proof.secret,
            }
            tags.append(Tag.parse(["proof", json.dumps(nut_proof)]))
            # send_proofs_json.append(nut_proof)

        # content = json.dumps(send_proofs_json)
        event = EventBuilder(Kind(9321), comment, tags).to_event(keys)
        #print(event.as_json())
        response = await send_event(event, client=client, dvm_config=dvm_config)

        print( bcolors.YELLOW + "[" + nut_wallet.name + "] Sent NutZap 🥜️⚡ with "+ str(amount) +" sats to "
               + PublicKey.parse(zapped_user).to_bech32() +
              "(" + response.id.to_hex() + ")" + bcolors.ENDC)



    except Exception as e:
        print(e)

    # await wallet2.redeem(send_proofs)
