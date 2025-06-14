"""Configuration constants for the Helix protocol."""

# Statement id of the genesis event shipped with the repository.  The
# corresponding file lives at ``helix/genesis.json``.  ``cli`` and the tests
# verify that this constant matches the SHA-256 digest of that file so that
# nodes agree on the parent hash of the very first event.
GENESIS_HASH = "4e17811011ec217ac84a9e037a82758a7de318342886a88a37ebabf90f52af73"

