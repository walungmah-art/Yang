import re
import random
import string
import uuid

from utils.constants import USER_AGENTS, TLS_PROFILES


# Per-user persistent fingerprints (muid stays same per machine)
_user_fingerprints = {}


def _detect_browser_info(ua: str) -> dict:
    """Extract browser name, version, and platform from user agent string."""
    info = {"browser": "Chrome", "version": "131", "platform": "Windows"}

    # Detect platform
    if "Macintosh" in ua or "Mac OS X" in ua:
        info["platform"] = "macOS"
    elif "Linux" in ua:
        info["platform"] = "Linux"
    else:
        info["platform"] = "Windows"

    # Detect browser + version
    if "Edg/" in ua:
        info["browser"] = "Edge"
        m = re.search(r'Edg/(\d+)', ua)
        if m: info["version"] = m.group(1)
    elif "OPR/" in ua:
        info["browser"] = "Opera"
        m = re.search(r'Chrome/(\d+)', ua)
        if m: info["version"] = m.group(1)
    elif "Firefox/" in ua:
        info["browser"] = "Firefox"
        m = re.search(r'Firefox/(\d+)', ua)
        if m: info["version"] = m.group(1)
    elif "Safari/" in ua and "Chrome" not in ua:
        info["browser"] = "Safari"
        m = re.search(r'Version/(\d+)', ua)
        if m: info["version"] = m.group(1)
    else:
        info["browser"] = "Chrome"
        m = re.search(r'Chrome/(\d+)', ua)
        if m: info["version"] = m.group(1)

    return info


def get_stripe_headers() -> dict:
    """Minimal Stripe-specific headers for use with curl_cffi impersonate.
    Browser headers (UA, sec-ch-ua, etc) are auto-set by curl_cffi."""
    return {
        "accept": "application/json",
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://checkout.stripe.com",
        "referer": "https://checkout.stripe.com/",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
    }


def get_headers(stripe_js: bool = False) -> dict:
    """Return headers mimicking Stripe.js browser requests."""
    ua = random.choice(USER_AGENTS)
    headers = {
        "accept": "application/json",
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://checkout.stripe.com",
        "referer": "https://checkout.stripe.com/",
        "user-agent": ua
    }
    if stripe_js:
        browser = _detect_browser_info(ua)
        v = browser["version"]
        platform = browser["platform"]

        headers["accept-language"] = random.choice([
            "en-US,en;q=0.9",
            "en-US,en;q=0.9,id;q=0.8",
            "en-GB,en;q=0.9,en-US;q=0.8",
            "en-US,en;q=0.9,nl;q=0.8",
            "en-US,en;q=0.9,de;q=0.8",
            "en-US,en;q=0.9,fr;q=0.8",
            "en-US,en;q=0.9,ja;q=0.8",
        ])
        headers["sec-fetch-dest"] = "empty"
        headers["sec-fetch-mode"] = "cors"
        headers["sec-fetch-site"] = "same-site"

        # Dynamic sec-ch-ua based on actual browser
        if browser["browser"] in ("Chrome", "Edge", "Opera"):
            not_a_brands = [
                '"Not(A:Brand";v="24"',
                '"Not_A Brand";v="8"',
                '"Not/A)Brand";v="8"',
                '"Not A(Brand";v="99"',
                '"Not)A;Brand";v="99"',
            ]
            not_a = random.choice(not_a_brands)
            if browser["browser"] == "Edge":
                headers["sec-ch-ua"] = f'"Chromium";v="{v}", {not_a}, "Microsoft Edge";v="{v}"'
            elif browser["browser"] == "Opera":
                headers["sec-ch-ua"] = f'"Chromium";v="{v}", {not_a}, "Opera";v="{v}"'
            else:
                headers["sec-ch-ua"] = f'"Chromium";v="{v}", {not_a}, "Google Chrome";v="{v}"'
            headers["sec-ch-ua-mobile"] = "?0"
            headers["sec-ch-ua-platform"] = f'"{platform}"'
        # Firefox/Safari don't send sec-ch-ua

    return headers


# Realistic Stripe.js build hashes (sampled from real CDN versions)
_STRIPE_CORE_HASHES = [
    "b4a8728ec3", "d1f02e4a7c", "9e3b5c1d8f", "a7c2e9f4b1", "3f8d6a2c5e",
    "c5e1b7d3a9", "f2a4c8e6d0", "7b9d3f1a5c", "e6c0a2d4f8", "1d5f9b3e7a",
    "8a2c6e0d4f", "4f0d8b2a6c", "b6e4a0c2d8", "2c8a4f6e0d", "d0f2c4a8e6",
]

_STRIPE_V3_HASHES = [
    "5a1c3e7d9b", "e8d0b2a4c6", "3c7a9d1e5f", "a0c4e8d2f6", "7d1f3a5c9e",
    "f4a6c0e2d8", "1e5a9d3f7b", "c2e6a0d4f8", "9b3d7f1a5c", "6e0d4f8a2c",
    "d8f2a6c0e4", "4a8c2e6d0f", "b0d4f8a2c6", "8c0e4a6d2f", "2f6a0c4e8d",
]


def _generate_stripe_hash() -> str:
    """Pick a realistic Stripe.js content hash from pool."""
    return random.choice(_STRIPE_CORE_HASHES)


def get_random_stripe_js_agent() -> str:
    """Get a Stripe.js payment_user_agent mimicking real browser.
    Uses two DIFFERENT hashes — one for core, one for v3 module."""
    core_hash = random.choice(_STRIPE_CORE_HASHES)
    v3_hash = random.choice(_STRIPE_V3_HASHES)
    return f"stripe.js%2F{core_hash}%3B+stripe-js-v3%2F{v3_hash}%3B+checkout"


def _rand_hex(length: int) -> str:
    return ''.join(random.choices(string.hexdigits[:16], k=length))


def _uuid_format() -> str:
    return f"{_rand_hex(8)}-{_rand_hex(4)}-4{_rand_hex(3)}-{random.choice('89ab')}{_rand_hex(3)}-{_rand_hex(12)}"


def generate_stripe_fingerprints(user_id: int = None) -> dict:
    """Generate Stripe.js fingerprint identifiers.
    muid is persistent per user (like browser cookies).
    guid is per-page-load. sid is per-session."""

    # muid persistent per user (simulates __stripe_mid cookie)
    if user_id and user_id in _user_fingerprints:
        muid = _user_fingerprints[user_id]
    else:
        muid = _uuid_format()
        if user_id:
            _user_fingerprints[user_id] = muid

    # guid = per page load, sid = per session
    guid = _uuid_format()
    sid = _uuid_format()

    return {"muid": muid, "guid": guid, "sid": sid}


def generate_eid() -> str:
    """Generate a valid UUID v4 for the eid parameter."""
    return str(uuid.uuid4())


def get_stripe_cookies(fp: dict) -> str:
    """Generate Stripe cookie header mimicking real browser."""
    return f"__stripe_mid={fp['muid']}; __stripe_sid={fp['sid']}"


def generate_session_context(user_id: int = None) -> dict:
    """Generate a complete session context for one checkout session.
    
    This should be called ONCE per checkout session and reused for ALL
    card attempts. Mimics a real user opening checkout in one browser.
    
    Returns dict with:
        - tls_profile: browser TLS profile (same browser for all cards)
        - fingerprints: muid/guid/sid (same page load for all cards)
        - cookies: stripe cookie header
        - payment_user_agent: stripe.js agent string
        - pasted_fields: which fields were pasted
        - time_on_page_base: base time user spent on page (increases per card)
    """
    # Pick ONE browser for the entire session
    tls_profile = random.choice(TLS_PROFILES)

    # Generate fingerprints ONCE (guid+sid stay same for all cards in session)
    fp = generate_stripe_fingerprints(user_id)

    # Cookies stay same for session
    cookies = get_stripe_cookies(fp)

    # Payment user agent stays same for session
    payment_user_agent = get_random_stripe_js_agent()

    # Randomize pasted_fields (some users type, some paste)
    pasted_fields = random.choice(["number", "number|cvc", "number|cvc|exp", ""])

    # Base time on page — starts at 20-60s, will increase per card
    time_on_page_base = random.randint(20000, 60000)

    return {
        "tls_profile": tls_profile,
        "fingerprints": fp,
        "cookies": cookies,
        "payment_user_agent": payment_user_agent,
        "pasted_fields": pasted_fields,
        "time_on_page_base": time_on_page_base,
    }
