# nutz

Attempt for NIP 60/61 (Nutwallet/NutZaps) implementation in Python

Work in Progress. Contributions welcome.
- Lightning funding source at the moment is LNBits so invoices can be paid in code (see .env_example). 
- If you don't enter a private key, a new one will be generated (recommended in current state)

TODOs:
- Move coins between mints (melt/mint) (right now we automatically mint new tokens from lightning, if proofs are not sufficient)
- Check various reasons why some mints reject minting
- Some events are not received.. (bug)
- Currently, using NIP04 for compatibility with nutsack.me, switch to NIP44 by setting legacy_encryption to False
