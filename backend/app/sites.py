"""The sites a user's US articles can be published to.

The admin picks one of these per user; the bot sends the key when minting and
the website turns it into a domain and stamps it on the article. Non-US
articles are unaffected and always go to the international domain.

These keys MUST match US_SITES in the website's config.py. Same arrangement as
MAX_NUMBERS_PER_USER and the website's MAX_WA_NUMBERS: two repos, one shared
vocabulary, and the receiving side rejects anything it does not recognise
rather than guessing.
"""

# (key, label shown in the admin dropdown). "" is the original destination, so
# every existing user keeps publishing exactly where they always have.
ARTICLE_SITES: list[tuple[str, str]] = [
    ("", "Default — beastaffiliates.com"),
    ("beastfinds", "Beast Finds — beastfinds.com"),
    ("beastscart", "Beast Cart — beastscart.com"),
    ("beastsdeal", "Beast Deals — beastsdeal.com"),
]

SITE_KEYS = {key for key, _ in ARTICLE_SITES}
