# nutz

Attempt for NIP 60/61 (Nutwallet/NutZaps) implementation in Python

Work in Progress. Contributions welcome.
- Funding source at the moment is LNBits (see .env_example). 
- If you don't enter a private key, a new one will be generated (recommended in current state)

TODOs:
- History of spending logic should be saved
- Advanced logic for when to claim proofs
- Move coins between mints (melt/mint) (right now we automatically mint new tokens from lightning, if proofs are not sufficient)
- add other funding sources
