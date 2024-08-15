# Pistachio Sack
(Pystachio, get it?)

Nostr NIP 60/61 (Nutsack) implementation in Python. 

Pistachios are members of the cashew family.

Work in Progress. Contributions welcome.
- Lightning Mint funding source at the moment is LNBits so invoices can be paid in code (see .env_example). 
- If you don't enter a private key, a new one will be generated (recommended in current state)
- for new accounts announce the profile with a valid ln address to melt (see main.py)

TODOs:
- Move coins between mints (melt/mint) (right now we automatically mint new tokens from lightning if proofs are not sufficient)
- Check various reasons why some mints reject minting
- Currently, using NIP04 for compatibility with nutsack.me, switch to NIP44 by setting legacy_encryption to False (Will do in future releases)
